# 基于Spark的北京市医疗机构资源整合与多维筛选可视化系统

本科毕业设计作品。整合北京市 9,789 家医疗机构的多源公开数据，基于 Spark 构建离线数仓。

系统分两条线，**主线是「就医决策」**，不是看图表：

1. **就医决策（任务主线）** — 说清症状与偏好 → 系统分诊出应就诊科室、按专科实力排序机构 → 挑 2–4 家横向对比 → 生成一份可打印、可带走的就医方案，方案自动留痕可回看。有任务态、有产出物。
2. **查阅支撑页（4 个）** — 找机构 / 资源画像 / 数据治理 / 系统说明，回答"有哪些机构、资源怎么分布、数据从哪来"。

两条线都有**两种形态**：在线（Vue 3 + Flask，数据可实时更新）与**零依赖单文件**
（`web/dashboard_offline.html`，一个 HTML 双击即用）。单文件形态同样具备完整主线——
判科与排序由前端本地复算，依据是内嵌的 Spark 科室实力指数与症状知识库，
因此**分享一个链接就能让别人的机器走完整个就医决策流程**。

## 技术栈

| 层 | 技术 |
|---|---|
| 数据处理 | PySpark 3.5.3（默认 `local[*]` 单机模式，可用 `SPARK_MASTER` 切回 Standalone 集群；Docker 原生 arm64） |
| 存储 | **HDFS 3.3.6**（ODS/DWD/DWS 分层 Parquet）+ **MySQL 8.0**（ADS 服务层结果） |
| 依赖管理 | Maven 坐标（`spark-submit --packages`，见 `spark/pom.xml`） |
| 服务 | Flask RESTful API（29 个接口） |
| 前端 | **Vue 3 + Vite**（前后端分离，`/spa/`）：1 条任务主线 + 4 个查阅支撑页；ECharts 5；另保留零依赖单文件离线大屏 |
| 部署 | Docker Compose |

## 目录结构

```
├── data/               # 数据目录（不入库，含原始数据与 processed 产物）
├── etl/                # 数据清洗/地理编码/科室字典脚本 + 入湖脚本
│   └── upload_to_hdfs.py   # 治理后 CSV / 行为日志 → HDFS ods/raw（数据入湖）
├── spark/              # PySpark 数仓作业
│   ├── jobs/           # 按「分层 + 分析维度」拆分（见下表）
│   ├── run_all.sh      # 全链路一键跑批（宿主机）
│   └── pom.xml         # 依赖清单（Maven 坐标）
├── docker/hadoop/      # 自建 arm64 HDFS 镜像（官方镜像仅 amd64，M1 上起不来）
├── web/                # Flask 应用（API）+ 两种前端形态
│   ├── app.py          # RESTful API（29 个接口：就医方案/筛选/排序/详情/概览/对比/地理编码/导诊/埋点）
│   ├── vue/            # Vue 3 前端工程（前后端分离形态，构建产物挂载在 /spa/）
│   │   ├── src/        # 源码：9 视图（PlanView 任务主线 + HubView 支撑页 + 7 子视图）+ 7 组件
│   │   ├── build.sh    # 一键构建 / 启动 dev server
│   │   └── dist/       # 构建产物（已入库，Flask 挂载点）
│   ├── templates/      # 单文件形态的 Flask 渲染版（与离线版同源）
│   └── static/         # ECharts、北京 geoJSON、样式
├── docs/               # 开发日志、项目说明书、功能点代码地图等文档
└── docker-compose.yml  # hdfs(namenode+datanode) + spark(master+worker) + mysql
```

### Spark 作业按分层 + 分析维度拆分

| 文件 | 职责 | 输入 → 输出 |
|---|---|---|
| `jobs/common.py` | 公共模块：SparkSession、HDFS 路径、读写封装 | — |
| `jobs/layer_ods.py` | ODS 层：原始数据列式化 | HDFS CSV → HDFS Parquet |
| `jobs/layer_dwd.py` | DWD 层：清洗 + 坐标关联 | HDFS Parquet → HDFS Parquet |
| `jobs/dim_space.py` | **空间维度**：区县分布、坐标覆盖、区间 Haversine 距离矩阵 | DWD → `dws/space/*` |
| `jobs/dim_category.py` | **类型/等级维度**：等级、类型、主办方结构 | DWD → `dws/category/*` |
| `jobs/dim_dept.py` | **科室维度**：科室覆盖度、科室×区分布、科室密度 | DWD → `dws/dept/*` |
| `jobs/dept_dict.py` | 科室名归一字典：200+ 种写法 → 49 个标准科室 + 大类 | — |
| `jobs/dim_dept_strength.py` | **科室实力指数**：national/municipal/feature/登记四来源归一 → 五级证据分级（国家/市级/官网/登记/已开设）+ 专科集中度，产出就医决策的排序依据 | DWD → `dws/dept/dept_strength` + MySQL `ads_dept_strength` |
| `jobs/dim_network.py` | **协作网络维度**：儿科医联体/卒中/危重新生儿/危重孕产妇 | DWD → `dws/network/*` |
| `jobs/dim_time.py` | **时间维度**：用户行为日趋势/时段/功能结构 + ETL 批次时效性快照 | 行为日志 → `dws/time/*` |
| `jobs/layer_ads.py` | ADS 服务层：分析结果落业务库 | HDFS → MySQL |
| `jobs/run_all.py` | 编排入口（单 SparkSession 串起 10 个阶段） | — |

## 快速开始

### 方式一：零依赖单文件形态（30 秒，推荐先看效果）

```bash
open web/dashboard_offline.html      # macOS；其他系统直接双击该文件
```

数据快照与主线数据包已内联进单个 HTML（约 8.3MB），**无需 Python、Docker、数据库、联网**，
即可使用七维筛选、四种排序、图表联动、导航栏视图切换与详情查看。

> 这是**单文件形态**，查阅与办事两种能力都具备：侧栏「就医决策」是完整的四步任务流
> （说需求 → 分诊排序 → 横向对比 → 拿方案），判科与排序由 `web/app.plan.js` 本地复算，
> 结果与在线接口 `/api/plan` 逐字一致（由 `etl/verify_offline_plan.py` 把关）。
> 在线形态（方式二）多出的是"数据可实时更新、方案存到数据库、AI 兜底可用"。

### 方式二：完整工程链路（HDFS + Spark + MySQL + Flask）

```bash
# 1. 安装 Web 依赖
pip install -r requirements.txt

# 2. 启动 HDFS（namenode + datanode）+ Spark 集群 + MySQL
docker compose up -d

# 3. 治理后数据入湖到 HDFS（ODS 原始层，含行为日志导出）
python etl/upload_to_hdfs.py

# 4. 提交数仓全链路作业：ODS → DWD → 空间/类型/科室/网络/时间 五维分析 → ADS 落 MySQL
bash spark/run_all.sh
#   （等价于容器内 spark-submit --packages com.mysql:mysql-connector-j:8.4.0 jobs/run_all.py）
#   单独重跑某阶段：bash spark/run_all.sh --only deptstrength  /  --from dwd
#   ⚠️ dim_dept_strength 是就医决策的排序依据，"改专科数据后"必须重跑该阶段

# 5. 重建查询索引（落库以 overwrite 模式写表会 DROP+CREATE，索引会丢失，此步必做）
python etl/create_indexes.py

# 5.5 加载智能导诊知识库维度（首跑或更新疾病词典后执行）
python etl/build_disease_dept_map.py     # 生成 data/processed/disease_dept_map.csv
python etl/load_disease_dept.py          # 写入 MySQL 维度表 dim_disease_dept

# 6. 导出离线就医决策数据包 + 重新生成单文件快照与产物
#    （动了 app.py 的判科/打分逻辑或 ads_dept_strength 时，导出这步不能省）
python etl/export_offline_plan_data.py
bash web/build_spa.sh

# 7. 构建 Vue 前端（前后端分离形态，产物挂载在 /spa/）
bash web/vue/build.sh

# 8. 启动 Web 服务
bash web/start.sh
# Vue 在线形态   → http://localhost:5001/spa/
# 单文件形态     → http://localhost:5001/
```

HDFS 分层结果可现场核验：

```bash
docker exec hdfs-namenode hdfs dfs -ls -R /hospital | head -30
docker exec hdfs-namenode hdfs dfs -du -s -h /hospital/ods /hospital/dwd /hospital/dws
```

验证服务是否就绪：`curl -s http://127.0.0.1:5001/api/health`
正常返回 `{"institutions":9789,"status":"ok"}`。

- Vue 在线形态（前后端分离）: http://localhost:5001/spa/
- 单文件离线大屏: http://localhost:5001/
- HDFS NameNode UI: http://localhost:9870
- Spark Master UI: http://localhost:8080
- Spark Worker UI: http://localhost:8081
- MySQL: localhost:3307（root/hospital123，应用账号 app/app123）

> Vue 工程说明（技术选型、目录结构、构建与排错）见 [`web/vue/README.md`](web/vue/README.md)。
> 更多运行方式（数据更新链路、常见坑、环境说明）见 [`docs/系统运行流程.md`](docs/系统运行流程.md)。

## API 一览

| 接口 | 说明 |
|---|---|
| `POST /api/plan` | **就医方案（任务主线核心）**：入参 `q` 症状描述 / `dept` 指定科室 + 偏好（`specialty`/`distance`/`level`/`balanced`）+ 位置与限制条件。返回分诊结论（应就诊科室及命中依据）+ 候选机构（含五级专科实力、匹配度、可解释的推荐依据）+ 评分构成 |
| `POST /api/plans` | 保存方案（留痕）→ `user_plan` 表，让"做过什么"可回溯。只接受 `ok=true` 的完整方案 |
| `GET /api/plans` | 我的方案列表（轻量，不含完整 payload） |
| `GET/DELETE /api/plans/<id>` | 读取 / 删除一份已保存方案 |
| `GET /api/institutions` | 七维筛选（区域/等级/类型/科室/协作网络/距离/名称）+ 排序（条件匹配度/距离/等级/科室数）+ 分页 |
| `GET /api/institutions/<id>` | 机构详情（含科室清单与重点专科标记） |
| `GET /api/overview/districts` / `levels` / `depts` | 区域/等级/科室覆盖概览 |
| `GET /api/specialty` | 重点专科医院列表 |
| `GET /api/meta/filters` | 筛选项可选值 |
| `GET /api/triage?q=<病情/疾病>` | **智能导诊**：输入病情或疾病名称，本地知识库匹配科室 → 联表筛选具备该科室的医院 → 加权评分排出 Top N；本地零命中时自动走大模型兜底。支持多轮对话：`&extra=` 追加澄清信息，返回 `reason_detail` 供前端摊开推荐理由 |
| `GET /api/inst/<id>/detail` | **机构详情**：联系方式（地址/电话/邮编/坐标）+ 就诊入口（114 平台 / 010-114 / 机构电话 / 高德导航）+ 特色科室（国家/市级/擅长三级）+ 周边配套（最近地铁站/停车场/公交站，高德 POI 实时查询）+ 实时状态（演示模拟） |
| `GET /api/inst/compare?ids=a,b,c` | **多机构横向对比**（2~4 家）：等级 / 类型 / 办别 / 区域 / 重点专科数 / 国家级 / 市级 / 科室数 / 距离（按当前定位或指定起始地址计算）/ 协作网络 / 专科清单 / 地址 / 电话 |
| `GET/POST /api/track` | 行为埋点（`ev`/`k1`/`k2`/`num`），落库 `fact_user_event`；单条 INSERT，失败静默，绝不影响主流程 |
| `GET /api/admin/stats` | **运营统计接口**（页面已下线、接口保留）：① 真实行为统计（热门搜索词 / 热门筛选区域 / 热门导诊病情 / 每日趋势，源自埋点）② 资源热度（区县密度 / 等级构成 / 专科覆盖 / 网络覆盖 / 办别构成） |
| `GET /api/about` | 关于页：数据规模、数仓表清单、Spark 清洗流程、公开数据来源、更新时间与更新日志 |
| `GET /api/ai/health` | 大模型探活（前端据此决定是否开启兜底；`?probe=1` 做真实连通测试） |
| `GET /api/ai/parse?q=<自然语言>` | 大模型把口语解析成筛选条件（规则引擎零命中时的兜底） |
| `GET /api/ai/advice?id=<机构id>` | **AI 就医提示**：严格基于该机构真实字段生成一段就医提示，提示词硬约束禁止输出医生姓名/职称/出诊时间/号源数量等未经核实信息 |
| `GET /api/ai/warm?queries=a\|b\|c` | 预热大模型缓存（演示/答辩前跑一次，之后同问零等待） |

距离计算采用 Haversine 公式（SQL 内实现）；条件匹配度（界面排序口径，原"综合评分"）= 0.5×等级 + 0.3×距离 + 0.2×科室数（归一化加权）。床位数因源数据覆盖率仅 0.4% 且取值疑似估算，已从展示与评分中移除，权重由等级维度承接。

**智能导诊（疾病/症状 → 科室 → 医院）**：基于本地知识库 `dim_disease_dept`（417 条常见病/症状 → 29 个标准科室的映射，含 39 条急诊条目与大量口语说法），输入自然语言病情（如"头痛""胸痛""儿童发烧"）即匹配对应科室，再联 `dwd_dept_relation_clean` 筛出具备该科室的医院，复用条件匹配度加权排出 Top N 并标注急诊优先。全程**离线零依赖**，不依赖大模型，断网可跑；维度表缺失时回退到 `data/processed/disease_dept_map.csv`。

**大模型兜底（Agnes AI，可选增强）**：本地知识库只覆盖高频病症，遇到口语长句（如"我父亲最近手抖得厉害人还瘦了一大圈"）会零命中。此时自动调用 **Agnes**（OpenAI 兼容协议）把病情映射到**库里真实存在的 29 个标准科室**（白名单由 `dwd_dept_relation_clean` 实时查询生成，避免模型返回库里没有的科室导致 0 结果），再复用同一套 SQL 与加权评分。设计原则是**离线为主、大模型兜底**：

- 主链路（规则引擎 + 本地知识库）**不依赖任何网络**，答辩断网照常演示；
- 大模型仅在本地零命中时触发，失败/限流一律**优雅降级**，绝不影响主流程；
- 结果按「内存 → MySQL `dim_ai_cache` → 接口」三级缓存，重复提问零额度、零等待（实测 3.6s → 0.05s），且重启服务后依然有效；
- 前端自动探活 `/api/ai/health`：离线单文件（`file://`）与在线静态版**永不发起网络请求**。

配置方式（三级优先）：环境变量 `AI_API_KEY` → 密钥文件 `data/.ai_key.txt`（已被 `.gitignore` 排除，**绝不入库**）。可选覆盖 `AI_API_BASE`（默认 `https://apihub.agnes-ai.com/v1`）、`AI_MODEL`（默认 `agnes-2.0-flash`）、`AI_TIMEOUT`；设 `AI_LLM_ENABLED=0` 可强制关闭，退回纯离线模式。

> **与就医决策的分工**：`/api/triage` 是"问一句答一串医院"的**查询式**导诊，保留为查阅能力；`/api/plan` 是**任务式**主线，有任务态、有比较、有产出物。两者共用同一套知识库与专科实力表，但打分权重不同（导诊重科室命中，方案重专科实力 + 距离 + 可比性），材料里不要混写。

> 模型选型实测：`agnes-2.0-flash` 平均约 4 秒、答案准确；`agnes-2.5-flash` 平均约 18 秒（最长 32 秒），不适合交互式场景，故默认用前者。
> 免费额度实测约 **1 次 / 30~40 秒**，现场连续提问会触发 429。演示前建议先预热：`bash web/start.sh` 后运行 `python etl/warm_ai_cache.py`（本地知识库已覆盖的问法会自动跳过，不浪费额度）。

**在线演示**：仓库内 `web/dashboard_offline.html` 是零依赖单文件形态（内联数据快照 + 离线就医决策数据包，约 8.3MB），
双击即可使用**完整的就医决策主线**（四步任务流）与 6 个查阅视图，无需启动任何服务。
GitHub Pages 上可直接访问：<https://brooke-boom.github.io/beijing-hospital-spark/web/dashboard_offline.html>
> 该形态主线的判科与排序由 `web/app.plan.js` 在浏览器本地复算，与在线接口 `/api/plan` 结果逐字一致
> （`etl/verify_offline_plan.py` 17 个用例把关）。不依赖后端的代价是：数据是构建时的快照、方案只存在浏览器本地、大模型兜底不可用。

**信息架构：1 条任务主线 + 4 个查阅支撑页**。左侧导航分「主线」与「查阅」两组，浅色/深色统一由设计令牌驱动：

| 层 | 入口 | 内容 |
|---|---|---|
| **主线** | ⭐ **就医决策** | 四步任务流：① 说需求（自然语言 + 位置 + 偏好 + 限制）② 看候选（分诊结论 + 候选机构卡：五级专科实力、匹配度、推荐依据）③ 做比较（2–4 家横向对比 11 项 + 设主选）④ 拿方案（可复制 / 下载 / 打印 / 保存的就医方案：机构·科室·地址·电话·距离·推荐依据·备选·就诊前准备·预约入口）；底部「我的方案」列出历史留痕 |
| 查阅 | 🏥 找机构 | 「机构列表」+「条件筛选」两个子标签：七维筛选、勾选对比、分页、机构详情抽屉、自然语言条件转换 |
| 查阅 | 📊 资源画像 | 「总览」+「结构分析」两个子标签：KPI、北京 16 区分级地图（点击联动筛选）、八维分析图表，全部随筛选实时联动 |
| 查阅 | 🗂 数据治理 | 「整合过程」+「质量核验」两个子标签：三类数据源与 Spark 八步流程时间线、8 个关键字段完整率、坐标精度分布、去重与多源交叉验证 |
| 查阅 | ℹ️ 系统说明 | 数据规模、公开数据来源、Spark 清洗流程、数仓分层表清单、更新时间与更新日志 |

> 旧路径（`#/institutions`、`#/overview` 等）已做 301 式重定向到对应支撑页，之前分享过的深链接不会失效。
> 数据治理两页所有数字均来自治理脚本真实输出（`data/processed/data_quality_report.md`），由 `build_spa.sh` 注入快照 `overviews.data_quality` 随离线大屏分发，非界面演示数据。

**专科实力指数（就医决策的排序依据，Spark 预计算）**：`jobs/dim_dept_strength.py` 把 `national_specialty` / `municipal_specialty` / `feature` / 登记关系四个来源归一到同一套科室字典，取每条(机构×科室)的最高证据等级：

| tier | 标签 | 来源 | MySQL 条数 |
|---|---|---|---|
| 4 | 国家临床重点专科 | `national_specialty` | 227 |
| 3 | 市级重点专科 | `municipal_specialty` | 218 |
| 2 | 官网重点科室 | `feature_level=1` | 266 |
| 1 | 登记重点专科 | `dwd_dept_relation_clean.is_key_specialty` | 2 |
| 0 | 已开设 | 登记关系基础层 | 16,016 |

`strength = 层级基准(80/64/46/28/10) + 机构等级微调(±8) + 协作网络(+4) + 专科集中度(≤8)`，结果落 `ads_dept_strength`（16,729 条 = 9,333 家 × 48 个标准科室）。
其中**专科集中度**= 本专科在该机构全部重点专科中的占比，用来打破"同层级同等级完全并列"——不加它，排序会退化成按机构名拼音排（实测"心慌胸闷"把中医医院排在阜外前面、"孕检"漏掉北京妇产医院）。

**机构详情抽屉**（点击列表任意一行右侧滑出，四个分区页签）：

- **概览**：基本信息、实时状态（**明确标注"演示模拟"**）、协作网络、同区科室数 TOP10 对比（红色标出本机构）
- **就诊与挂号**：114 统一平台入口、010-114 电话预约、机构电话、高德一键导航、地址与坐标
- **重点专科**：国家级 / 北京市级 / 擅长科室三级清单 + 科室明细表（含是否重点专科与来源）
- **周边配套**：最近地铁站 / 附近停车场 / 附近公交站，来自**高德 POI 实时查询**（含距离、按 75 米/分钟估算的步行时间、独立导航按钮），结果按坐标网格（~100m）缓存进 `dim_poi_cache` 避免重复消耗额度

**机构横向对比**：列表勾选 2~3 家 → 底部浮条 → 对比表。共 16 个对比项，其中数值型（重点专科数 / 国家级 / 市级 / 科室数 / 距离）自动判定"越高越好 / 越近越好"并用绿色标出最优值；距离按当前定位或指定起始地址计算，保证横向可比。

> **关于"名医推荐"的工程取舍**：公开数据中**没有可靠的医生姓名 / 职称 / 出诊信息来源**，凭空生成属于事实性错误，在答辩与实用场景中都会造成误导。因此系统**不收录、不编造任何医生个人信息**，改为把「**真实重点专科清单 → 官方挂号入口**」直接打通：每家机构的特色科室均来自官方公示名单，点击即可跳转 114 平台按机构名检索该科真实出诊专家。`/api/ai/advice` 的提示词也硬性禁止模型输出医生姓名与任何未经核实的具体数字。

**多维分析视图**（全量 9,789 家机构）：办别分布（3,085 / 5,323 / 1,381）、重点专科分级（77 / 166 / 2,111 / 7,435）、协作网络覆盖（7 / 46 / 76 / 8 / 20）、等级 × 办别交叉、专科能力 TOP10（按 `key_specialty_count` 排名）、区域 × 等级堆叠、坐标精度（高精度 / 粗略 / 缺失，直观呈现数据治理成效）、科室覆盖 TOP15（源自 `feature` + `key_depts`）。筛选任一条件（如"三级 + 海淀区"），上述八张图与四项 KPI 立即重算，体现"资源整合后多视角穿透分析"的设计目标。

## 系统架构

```
多源 CSV/XLSX ─治理─▶ data/processed/*.csv ─入湖─▶ HDFS /hospital/ods/raw
                                                        │
                            ┌───────────────────────────┴────────────────────────┐
                            ▼                                                    │
                    Spark 数仓分层（Standalone 集群）                             │
         ODS Parquet ─▶ DWD 清洗关联 ─▶ DWS 五维分析 ─▶ ADS 服务层               │
        /hospital/ods   /hospital/dwd    /hospital/dws    （HDFS 承载①②层，
                                                           结果落 MySQL④）
                            │
              ECharts 可视化 ◀── Flask API ◀── MySQL（ADS 服务层）
                            │
                  build_spa.sh → 单文件离线大屏（快照注入）
```

存储职责划分（对应复盘标准 ①②④）：

| 层 | 存储位置 | 内容 |
|---|---|---|
| 原始层 | HDFS `/hospital/ods/raw` | 治理后 CSV + 行为日志（文本，可回溯） |
| ODS | HDFS `/hospital/ods/parquet` | 原始数据列式化 Parquet |
| DWD | HDFS `/hospital/dwd` | 清洗 + 坐标关联后的明细 |
| DWS | HDFS `/hospital/dws/{space,category,dept,network,time}` | 五个分析维度的汇总结果 |
| ADS | **MySQL** `hospital` 库 | 服务层宽表与分析结果，供 Flask 查询 |
| 元数据 | HDFS `/hospital/meta/snapshots` | 每批次 ETL 快照（时效性维度） |

> 说明：全部数据来自公开渠道清洗整合，无虚构模拟数据。对覆盖率不足或真实性存疑的字段（如床位数）采取"宁缺勿伪"原则，直接移除展示并在论文中说明，而非以估算值填充。

## 状态

- [x] 数据清洗整合（70 文件 → 9,789 家机构主表）
- [x] 科室字典（32 标准科室 / 11 大类 / 16,251 条映射，重点专科 68 家权威口径）
- [x] Docker Spark 集群搭建与验证
- [x] **HDFS 3.3.6 集群**（自建 arm64 镜像，namenode + datanode，数据入湖 `/hospital/ods/raw`）
- [x] **PySpark 数仓分层（HDFS 承载）：ODS 6 表 → DWD 3 表 → DWS 五个分析维度 → ADS 服务层落 MySQL**
- [x] **分析代码按维度拆分**（`jobs/dim_space|category|dept|network|time.py`，五维独立可跑）
- [x] **Maven 依赖管理**（`spark-submit --packages com.mysql:mysql-connector-j:8.4.0`，替代手工 `--jars`）
- [x] 地理编码（9,787/9,789 = 99.98%，高德 API 断点续跑，缺失 2 家地址不规范）
- [x] Flask 筛选排序 API + ECharts 可视化
- [x] 单文件离线大屏（build_spa.sh 构建链路）
- [x] district 字段治理（41 家空区 → 100% 完整）
- [x] 数据可信度联网验证（与市/区卫健委官方口径横向对比，详见 docs/毕业论文.md 5.3.1）
- [x] 国家临床重点专科联网增强（43 家医院 / 229 条，新增 national_specialty 字段并在详情浮层展示）
- [x] feature 字段反向补全（17 家 / +78 条，ads_specialty_hospital 418 → 496 条，两套专科口径自洽）
- [x] 市/区级临床重点专科联网增强（**77 家医院 / 283 条**，新增 municipal_specialty 字段并在详情浮层展示；中医"十四五"首批 74 项 + 第二批 107 项全部抓齐）
- [x] 三层专科口径自洽（feature 擅长分级 → national_specialty 国家级 → municipal_specialty 市/区级，50 家 municipal_only 补足先前无国家级认定的三级医院）
- [x] **智能导诊能力**（疾病/症状 → 科室 → 医院，本地知识库 417 条 / 29 科室 / 39 急诊条目，`dim_disease_dept` 维度表 + `/api/triage` 接口，离线零依赖；独立页面在 v5.0 信息架构重构中下线，接口与知识库完整保留）
- [x] **可视化大屏导航栏 + 多维分析视图**（左侧七视图导航：数据总览 / 医疗资源分析 / 机构查询 / 智能筛选 / 数据整合 / 数据质量 / 系统说明；医疗资源分析含八维分析图表 + 四项 KPI，全部随七维筛选实时联动，ECharts 渲染）
- [x] **v5.0 信息架构重构**（2026-09-18：导航重构为七视图，与论文题目一一对应；新增机构查询 / 智能筛选 / 数据整合 / 数据质量四个独立页面）
- [x] **机构详情抽屉**（概览 / 就诊与挂号 / 重点专科 / 周边配套 四个分区页签；周边配套接入高德 POI 实时查询并按坐标网格缓存至 `dim_poi_cache`）
- [x] **机构横向对比**（勾选 2~3 家 → 16 项对比表，数值项自动判定优劣并高亮最优值，距离按当前定位或指定起始地址计算）
- [x] **智能导诊多轮对话**（追问澄清 + `reason_detail` 摊开加权评分；知识库扩充至 417 条 / 29 科室）
- [x] **行为埋点与运营统计**（`fact_user_event` 真实行为埋点 + 资源热度双板块；`/api/track` 单条 INSERT 失败静默，绝不影响主流程；独立运营后台页在 v5.0 重构中下线，`/api/admin/stats` 接口保留）
- [x] **关于页**（数据来源、Spark 七步清洗流程、数仓分层表清单、更新时间与更新日志，全部取自真实表）

> **数据可信度**（2026-09-10 联网核实）：以北京市医保 A 类定点医疗机构名单（2026-08-08，58 项）为基准交叉验证，本系统**覆盖率 100%、等级标注正确率 100%**；主表 9,789 家与官方全量口径的差额主要为基层机构（村卫生室/社区卫生服务站）覆盖度差异，属统计口径不同而非数据错误，详见 `docs/数据联网核实报告.md`。当前等级分布：三级 213 / 二级 212 / 一级 833 / 未定级 31 / 不适用医院分级 8,500。
