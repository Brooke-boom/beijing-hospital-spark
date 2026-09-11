# 基于 Spark 的北京市医院医疗资源整合与多维筛选可视化系统

本科毕业设计作品。整合北京市 9,789 家医疗机构的多源公开数据，基于 Spark 构建离线数仓，提供区域/等级/类型/科室/距离多维筛选与多策略排序的可视化查询系统。

## 技术栈

| 层 | 技术 |
|---|---|
| 数据处理 | PySpark 3.5.3（Standalone 集群，Docker 原生 arm64） |
| 存储 | MySQL 8.0（ODS/DWD/DWS/ADS 四层数仓） |
| 服务 | Flask RESTful API |
| 前端 | ECharts 5（北京地图散点 + 柱状 + 环形图） |
| 部署 | Docker Compose |

## 目录结构

```
├── data/               # 数据目录（不入库，含原始数据与 processed 产物）
├── etl/                # 数据清洗/地理编码/科室字典脚本
├── spark/              # PySpark 作业脚本（数仓分层 ETL）
├── web/                # Flask 应用（API + 可视化前端）
│   ├── app.py          # RESTful API（筛选/详情/概览）
│   ├── templates/      # 单页前端
│   └── static/         # ECharts、北京 geoJSON、样式
├── docs/               # 开发日志等文档
└── docker-compose.yml  # spark-master + spark-worker + mysql 编排
```

## 快速开始

### 方式一：零依赖离线大屏（30 秒，推荐先看效果）

```bash
open web/dashboard_offline.html      # macOS；其他系统直接双击该文件
```

数据快照已内联进单个 HTML（约 6.5MB），**无需 Python、Docker、数据库、联网**，
即可使用七维筛选、四种排序、图表联动与详情查看。

### 方式二：完整工程链路（Spark + MySQL + Flask）

```bash
# 1. 安装 Web 依赖
pip install -r requirements.txt

# 2. 启动 Spark 集群 + MySQL
docker compose up -d

# 3. 提交数仓 ETL（CSV → ODS → DWD → DWS → ADS → MySQL）
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --jars /opt/workspace/jobs/mysql-connector-j-8.4.0.jar \
  --driver-class-path /opt/workspace/jobs/mysql-connector-j-8.4.0.jar \
  /opt/workspace/jobs/etl_hospital.py

# 4. 重建查询索引（ETL 以 overwrite 模式写表会 DROP+CREATE，索引会丢失，此步必做）
python etl/create_indexes.py

# 4.5 加载智能导诊知识库维度（首跑或更新疾病词典后执行）
python etl/build_disease_dept_map.py     # 生成 data/processed/disease_dept_map.csv
python etl/load_disease_dept.py          # 写入 MySQL 维度表 dim_disease_dept

# 5. 重新生成快照与离线大屏
bash web/build_spa.sh

# 6. 启动 Web 服务
bash web/start.sh
# 浏览器访问 http://localhost:5001
```

验证服务是否就绪：`curl -s http://127.0.0.1:5001/api/health`
正常返回 `{"institutions":9789,"status":"ok"}`。

- 系统界面: http://localhost:5001
- Spark Master UI: http://localhost:8080
- Spark Worker UI: http://localhost:8081
- MySQL: localhost:3307（root/hospital123，应用账号 app/app123）

> 更多运行方式（数据更新链路、常见坑、环境说明）见 [`docs/系统运行流程.md`](docs/系统运行流程.md)。

## API 一览

| 接口 | 说明 |
|---|---|
| `GET /api/institutions` | 七维筛选（区域/等级/类型/科室/协作网络/距离/名称）+ 排序（综合评分/距离/等级/科室数）+ 分页 |
| `GET /api/institutions/<id>` | 机构详情（含科室清单与重点专科标记） |
| `GET /api/overview/districts` / `levels` / `depts` | 区域/等级/科室覆盖概览 |
| `GET /api/specialty` | 重点专科医院列表 |
| `GET /api/meta/filters` | 筛选项可选值 |
| `GET /api/triage?q=<病情/疾病>` | **智能导诊**：输入病情或疾病名称，本地知识库匹配科室 → 联表筛选具备该科室的医院 → 加权评分排出 Top N |

距离计算采用 Haversine 公式（SQL 内实现）；综合评分 = 0.5×等级 + 0.3×距离 + 0.2×科室数（归一化加权）。床位数因源数据覆盖率仅 1.5% 且取值疑似估算，已从展示与评分中移除，权重由等级维度承接。

**智能导诊（疾病/症状 → 科室 → 医院）**：基于本地知识库 `dim_disease_dept`（262 条常见病/症状 → 29 个标准科室的映射，覆盖 33 条急诊条目），输入自然语言病情（如"头痛""胸痛""儿童发烧"）即匹配对应科室，再联 `dwd_dept_relation_clean` 筛出具备该科室的医院，复用综合评分排出 Top N 并标注急诊优先。全程**离线零依赖**，不依赖大模型，断网可跑；维度表缺失时回退到 `data/processed/disease_dept_map.csv`。

**在线演示**：仓库内 `web/dashboard_offline.html` 为零依赖单文件离线大屏（数据快照内联，约 6.6MB），可直接打开浏览完整可视化界面，无需启动任何服务。也可访问 GitHub Pages 在线版。

## 系统架构

```
多源 CSV/XLSX → Spark ETL 清洗整合 → ODS → DWD → DWS → ADS
                                                      ↓
              ECharts 可视化 ← Flask API ← MySQL（ADS 层）
                                                      ↓
                          build_spa.sh → 单文件离线大屏（快照注入）
```

> 说明：全部数据来自公开渠道清洗整合，无虚构模拟数据。对覆盖率不足或真实性存疑的字段（如床位数）采取"宁缺勿伪"原则，直接移除展示并在论文中说明，而非以估算值填充。

## 状态

- [x] 数据清洗整合（70 文件 → 9,789 家机构主表）
- [x] 科室字典（32 标准科室 / 11 大类 / 16,251 条映射，重点专科 68 家权威口径）
- [x] Docker Spark 集群搭建与验证
- [x] PySpark 数仓分层（ODS 5 表 → DWD 3 表 → DWS 4 表 → ADS 4 表）
- [x] 地理编码（9,787/9,789 = 99.98%，高德 API 断点续跑，缺失 2 家地址不规范）
- [x] Flask 筛选排序 API + ECharts 可视化
- [x] 单文件离线大屏（build_spa.sh 构建链路）
- [x] district 字段治理（41 家空区 → 100% 完整）
- [x] 数据可信度联网验证（与市/区卫健委官方口径横向对比，详见 docs/毕业论文.md 5.3.1）
- [x] 国家临床重点专科联网增强（43 家医院 / 229 条，新增 national_specialty 字段并在详情浮层展示）
- [x] feature 字段反向补全（17 家 / +78 条，ads_specialty_hospital 418 → 496 条，两套专科口径自洽）
- [x] 市/区级临床重点专科联网增强（**77 家医院 / 283 条**，新增 municipal_specialty 字段并在详情浮层展示；中医"十四五"首批 74 项 + 第二批 107 项全部抓齐）
- [x] 三层专科口径自洽（feature 擅长分级 → national_specialty 国家级 → municipal_specialty 市/区级，50 家 municipal_only 补足先前无国家级认定的三级医院）
- [x] **智能导诊模块**（疾病/症状 → 科室 → 医院，本地知识库 262 条 / 29 科室 / 33 急诊条目，`dim_disease_dept` 维度表 + `/api/triage` 接口 + 大屏「智能导诊」面板，离线零依赖）

> **数据可信度**（2026-09-10 联网核实）：以北京市医保 A 类定点医疗机构名单（2026-08-08，58 项）为基准交叉验证，本系统**覆盖率 100%、等级标注正确率 100%**；主表 9,789 家与官方全量口径的差额主要为基层机构（村卫生室/社区卫生服务站）覆盖度差异，属统计口径不同而非数据错误，详见 `docs/数据联网核实报告.md`。当前等级分布：三级 212 / 二级 212 / 一级 833 / 不适用 0 / 未定级 30。
