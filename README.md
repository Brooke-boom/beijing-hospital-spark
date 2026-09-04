# 基于 Spark 的北京市医院医疗资源整合与智能筛选可视化系统

本科毕业设计作品。整合北京市 9,811 家医疗机构的多源公开数据，基于 Spark 构建离线数仓，提供区域/等级/类型/科室/距离多维筛选与多策略排序的可视化查询系统。

## 技术栈

| 层 | 技术 |
|---|---|
| 数据处理 | PySpark 3.5.3（Standalone 集群，Docker 原生 arm64） |
| 存储 | HDFS/Hive（过程层）→ MySQL 8.0（ADS 结果层） |
| 服务 | Flask RESTful API |
| 前端 | ECharts + 高德 JS API |
| 部署 | Docker Compose |

## 目录结构

```
├── data/               # 数据目录（不入库，含原始数据与 processed 产物）
├── etl/                # 数据清洗/地理编码/科室字典脚本
├── spark/              # PySpark 作业脚本（验证脚本 + 数仓分层）
├── docs/               # 开发日志、论文大纲等文档
├── docker-compose.yml  # spark-master + spark-worker + mysql 编排
└── web/                # Flask 应用（规划中）
```

## 快速开始

```bash
docker compose up -d          # 启动 Spark 集群 + MySQL
# 提交验证作业
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 /opt/workspace/jobs/verify_spark.py
```

- Spark Master UI: http://localhost:8080
- Spark Worker UI: http://localhost:8081
- MySQL: localhost:3307（root/hospital123）

## 系统架构

```
多源 CSV/XLSX → Spark ETL 清洗整合 → ODS → DWD → DWS → ADS
                                                      ↓
              ECharts 可视化 ← Flask API ← MySQL（ADS 层）
```

> 说明：负载类指标为模拟数据（方法与依据见论文 4.5 节），其余数据来自公开渠道清洗整合。

## 状态

- [x] 数据清洗整合（70 文件 → 9,791 家机构主表）
- [x] 科室字典（32 标准科室 / 11 大类 / 16,310 条映射）
- [x] Docker Spark 集群搭建与验证
- [ ] 地理编码（进行中：3,850/9,791）
- [ ] PySpark 数仓分层
- [ ] Flask 筛选排序 API
- [ ] ECharts 可视化大屏
