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

```bash
# 1. 启动 Spark 集群 + MySQL
docker compose up -d

# 2. 提交数仓 ETL（CSV → ODS → DWD → DWS → ADS → MySQL）
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --jars /opt/workspace/jobs/mysql-connector-j-8.4.0.jar \
  --driver-class-path /opt/workspace/jobs/mysql-connector-j-8.4.0.jar \
  /opt/workspace/jobs/etl_hospital.py

# 3. 启动 Web 服务
pip install -r web/requirements.txt
python web/app.py
# 浏览器访问 http://localhost:5001
```

- 系统界面: http://localhost:5001
- Spark Master UI: http://localhost:8080
- Spark Worker UI: http://localhost:8081
- MySQL: localhost:3307（root/hospital123，应用账号 app/app123）

## API 一览

| 接口 | 说明 |
|---|---|
| `GET /api/institutions` | 多维筛选（区域/等级/类型/科室/名称）+ 排序（综合评分/距离/等级/床位/科室数）+ 分页 |
| `GET /api/institutions/<id>` | 机构详情（含科室清单与重点专科标记） |
| `GET /api/overview/districts` / `levels` / `depts` | 区域/等级/科室覆盖概览 |
| `GET /api/specialty` | 重点专科医院列表 |
| `GET /api/meta/filters` | 筛选项可选值 |

距离计算采用 Haversine 公式（SQL 内实现）；综合评分 = 0.4×等级 + 0.3×距离 + 0.2×床位 + 0.1×科室数（归一化加权）。

**在线演示**：仓库内 `web/dashboard_offline.html` 为零依赖单文件离线大屏（数据快照内联，约 4.8MB），可直接打开浏览完整可视化界面，无需启动任何服务。

## 系统架构

```
多源 CSV/XLSX → Spark ETL 清洗整合 → ODS → DWD → DWS → ADS
                                                      ↓
              ECharts 可视化 ← Flask API ← MySQL（ADS 层）
                                                      ↓
                          build_spa.sh → 单文件离线大屏（快照注入）
```

> 说明：全部数据来自公开渠道清洗整合；床位数经多源证据池回填（完整率有限），无虚构模拟数据。

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

> **数据可信度**（2026-09-06 联网核实）：主表 9,789 家 vs 官方 12,062（2024），差 −2,273 主要为基层（村卫生室/卫生服务站）覆盖度差异；三级 202 家 vs 官方 150，本地通过多源融合纳入部队医院、民营三甲及未公开的二级升三级医院，三级覆盖度优于单一公开渠道。
