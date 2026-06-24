# XCMG Manufacturing RCA Agent

> 制造业根因分析智能体 — 基于 LangGraph 风格工作流的开源项目

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 项目概述

XCMG-MFG-RCA-Agent 是一个面向制造业的根因分析（Root Cause Analysis）智能体系统。它采用 **LangGraph 风格的有向图工作流**，结合 **MCP 风格工具调用**、**Skills SOP 知识库**、**RAG 混合检索** 和 **Text2SQL 安全查询**，自动分析 MES/APS/WMS/QMS 系统中的生产异常事件，定位根因并生成分析报告。

### 核心特性

- **8 节点 RCA 工作流**：`analyze_symptom → generate_hypotheses → select_tool → execute_tool → observe_evidence → draft_rca → reflect → generate_report`，支持反思循环
- **MCP 风格工具系统**：工单查询、设备维保、物料库存、接口日志、质量记录、知识检索、Text2SQL
- **Skills SOP 配置**：6 种异常类型的 YAML 定义（超站检查、设备冲突、物料短缺、质量异常、接口超时、排程风险）
- **RAG 混合检索**：关键词召回 + 真实 Embedding 向量检索 + Reranker 重排序
- **Text2SQL 安全查询**：只读 SELECT 生成 + 白名单验证 + PostgreSQL 执行
- **PostgreSQL 持久化**：任务、报告、检查点、工具去重
- **Docker Compose + K8s**：开箱即用的容器化部署方案

## 架构概览

```
                          ┌─────────────────────────────┐
                          │       FastAPI Server         │
                          │   POST /api/v1/rca/analyze   │
                          └─────────────┬───────────────┘
                                        │
                          ┌─────────────▼───────────────┐
                          │      RCAWorkflow.run()       │
                          │                              │
                          │  ┌──────────────────────┐    │
                          │  │ 1. analyze_symptom   │    │
                          │  │ 2. generate_hypotheses│   │
                          │  │ 3. select_tool       │◄───┤ reflection loop
                          │  │ 4. execute_tool      │    │ (max 3 rounds)
                          │  │ 5. observe_evidence  │    │
                          │  │ 6. draft_rca         │    │
                          │  │ 7. reflect ──────────┼────┘
                          │  │ 8. generate_report   │    │
                          │  └──────────────────────┘    │
                          └─────────────┬───────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
┌─────────▼─────────┐  ┌───────────────▼───────────────┐  ┌─────────▼─────────┐
│   MCP Tools       │  │        RAG Service            │  │   Text2SQL        │
│ ┌───────────────┐ │  │ ┌───────────────────────────┐ │  │ ┌───────────────┐ │
│ │ workorder     │ │  │ │ HybridRetriever           │ │  │ │ SQLGenerator  │ │
│ │ resource      │ │  │ │  - Keyword scoring        │ │  │ │ SQLValidator  │ │
│ │ material      │ │  │ │  - Embedding vector search│ │  │ │ SQLExecutor   │ │
│ │ interface_log │ │  │ │  - Reranker               │ │  │ └───────────────┘ │
│ │ quality       │ │  │ └───────────────────────────┘ │  └───────────────────┘
│ │ knowledge     │ │  │                               │
│ │ text2sql      │ │  │   Skills SOP (YAML)           │
│ └───────────────┘ │  │   ┌───────────────────────┐   │
└───────────────────┘  │   │ overstation_check     │   │
                        │   │ equipment_conflict    │   │
┌───────────────────┐  │   │ material_shortage     │   │
│   Persistence     │  │   │ quality_abnormal      │   │
│ ┌───────────────┐ │  │   │ interface_timeout     │   │
│ │ PostgreSQL    │ │  │   │ schedule_risk         │   │
│ │ Checkpointer  │ │  │   └───────────────────────┘   │
│ │ Repositories  │ │  └───────────────────────────────┘
│ └───────────────┘ │
└───────────────────┘
```

## 已实现功能

| 模块 | 功能 | 状态 |
|------|------|------|
| 工作流 | 8 节点 LangGraph 风格 RCA 工作流 | ✅ |
| 工作流 | 反思循环（最多 3 轮） | ✅ |
| 工具 | 7 个 MCP 风格工具（工单/资源/物料/接口/质量/知识/Text2SQL） | ✅ |
| 工具 | 工具注册中心（单例模式） | ✅ |
| Skills | 6 种异常类型 YAML SOP 定义 | ✅ |
| RAG | 混合检索（关键词 + Embedding 向量 + Reranker 重排序） | ✅ |
| RAG | Markdown 知识文档加载和分块 | ✅ |
| Text2SQL | 模板驱动 SQL 生成 | ✅ |
| Text2SQL | 安全验证（只读 SELECT + 白名单 + LIMIT） | ✅ |
| Text2SQL | PostgreSQL 执行器 | ✅ |
| 持久化 | PostgreSQL 任务/报告/检查点/去重表 | ✅ |
| 持久化 | 检查点保存和恢复 | ✅ |
| API | FastAPI 4 个端点（health/analyze/reports/tasks） | ✅ |
| 部署 | Dockerfile + docker-compose.yml | ✅ |
| 部署 | K8s manifests（Deployment/Service/Ingress/HPA/ConfigMap） | ✅ |
| 数据 | 示例 MES/APS/WMS/QMS 数据 | ✅ |
| 测试 | 冒烟测试和单元测试 | ✅ |

## 计划功能

以下功能为生产环境扩展预留：

| 功能 | 说明 |
|------|------|
| Worker 异步池 | 将 RCA 任务从同步执行改为 Celery/Redis 异步任务队列 |
| SSO/JWT 认证 | 集成企业单点登录和 JWT Token 鉴权 |
| 真实系统集成 | 对接实际 MES/APS/WMS/QMS 系统 API |
| 多租户 | 支持多工厂/多组织隔离 |
| 趋势分析 | 基于历史 RCA 数据的根因趋势和模式挖掘 |
| LLM 集成 | 接入大语言模型增强假设生成和报告质量 | ✅ |
| pgvector | 使用 PostgreSQL/pgvector 保存知识库 Embedding 向量 | ✅ |
| 实时监控 | WebSocket 推送工作流执行状态 |

## 快速开始

### 环境要求

- Python 3.10+
- pip
- PostgreSQL 14+（本地或 Docker Compose）

### 1. 安装依赖

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
```

项目依赖统一维护在 `pyproject.toml` 中，`python -m pip install -e .` 会自动同步安装 `[project] dependencies` 中声明的所有运行时依赖。

### 2. 配置 PostgreSQL 与大模型

复制 `.env.example` 为 `.env`，至少配置：

```env
DATABASE_URL=postgresql://rca_user:rca_password@localhost:5432/xcmg_rca
DATABASE_SCHEMA=rca
LLM_API_KEY=sk-your-key-here
EMBEDDING_API_KEY=sk-your-key-here
VECTOR_DB_PROVIDER=pgvector
VECTOR_DATABASE_URL=postgresql://rca_user:rca_password@localhost:5432/xcmg_rca
VECTOR_DB_SCHEMA=rca_vector
```

### 3. 初始化数据库结构

数据库结构不会在应用启动时自动创建。首次部署或重建数据库时，需要先手动执行 `db/` 下的 SQL 脚本：

```powershell
psql "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca" -f db/001_init_app_schema.sql
psql "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca" -f db/002_init_business_schema.sql
psql "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca" -f db/004_init_vector_schema.sql
psql "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca" -f db/003_init_metadata_seed.sql
```

其中：

- `db/001_init_app_schema.sql` 创建 RCA 应用表（任务、报告、反馈、检查点、聊天）和元数据层表（数据源、表结构、字段含义、业务术语等）。
- `db/002_init_business_schema.sql` 创建示例业务表（工单、设备维保、物料库存、质量记录、接口日志），仅用于本地开发/演示。
- `db/004_init_vector_schema.sql` 启用 `pgvector` 扩展并创建向量表（时间戳默认值已统一为日期零点精度）。
- `db/003_init_metadata_seed.sql` 插入元数据初始数据（数据源、字段映射、业务术语、关联关系、指标定义、查询模板）。
- 使用 Docker Compose 首次创建 PostgreSQL 数据卷时，`db/` 目录会挂载到容器初始化目录自动执行；已有数据卷不会重复执行。

### 4. 插入示例数据

```bash
python app/scripts/init_sample_db.py
```

### 5. 运行演示

```bash
python app/scripts/run_demo.py
```

### 6. 启动 API 服务

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. 运行测试

```bash
python app/scripts/smoke_test.py
```

或使用 pytest：

```bash
pip install pytest
pytest app/tests/ -v
```

## API 示例

### 健康检查

```bash
curl http://localhost:8000/api/v1/rca/health
```

响应：
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2024-06-21T10:00:00"
}
```

### 执行 RCA 分析

```bash
curl -X POST http://localhost:8000/api/v1/rca/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "anomaly_type": "overstation_check",
      "description": "工位 WS-03 连续 3 小时超站，影响下游 5 个工位",
      "source_system": "MES"
    }
  }'
```

响应：
```json
{
  "task_id": "rca-a1b2c3d4e5f6",
  "status": "completed",
  "message": "RCA 分析完成，置信度: 85%"
}
```

### 查询报告

```bash
curl http://localhost:8000/api/v1/rca/reports/rca-a1b2c3d4e5f6
```

### 查询任务状态

```bash
curl http://localhost:8000/api/v1/rca/tasks/rca-a1b2c3d4e5f6
```

## Docker Compose 使用

Docker Compose 只部署 RCA API，PostgreSQL 使用现成外部数据库。部署前复制 `.env.example` 为 `.env`，然后修改数据库和大模型参数：

- `DATABASE_URL`、`BUSINESS_DATABASE_URL`、`VECTOR_DATABASE_URL` 均需指向容器可访问的 PostgreSQL 地址。
- 三个 PostgreSQL URL 只填连接信息，schema 由 `DATABASE_SCHEMA`、`BUSINESS_DATABASE_SCHEMA`、`VECTOR_DB_SCHEMA` 单独控制。
- 大模型相关参数按实际服务修改 `LLM_*`、`EMBEDDING_*`、`RERANKER_*`。

示例：

```env
DATABASE_URL=postgresql://rca_user:rca_password@postgres.example.com:5432/xcmg_rca
BUSINESS_DATABASE_URL=postgresql://rca_user:rca_password@postgres.example.com:5432/xcmg_rca
VECTOR_DATABASE_URL=postgresql://rca_user:rca_password@postgres.example.com:5432/xcmg_rca
LLM_PROVIDER=compatible
LLM_MODEL=your-model
LLM_BASE_URL=https://your-llm-endpoint/v1
LLM_API_KEY=your-api-key
EMBEDDING_PROVIDER=compatible
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_BASE_URL=https://your-embedding-endpoint/v1
EMBEDDING_API_KEY=your-api-key
RERANKER_PROVIDER=compatible
RERANKER_MODEL=your-reranker-model
RERANKER_BASE_URL=https://your-reranker-endpoint
RERANKER_API_KEY=your-api-key
```

必须从 `deploy/docker` 目录启动，并显式传入根目录 `.env`，这样 Compose 变量替换和 API 容器环境变量会使用同一份配置：

```bash
docker compose --env-file ../../.env up -d --build
```

健康检查：

```bash
curl http://localhost:8000/api/v1/rca/health
```

## K8s 部署

`k8s/` 目录包含完整的 Kubernetes 部署清单：

| 文件 | 说明 |
|------|------|
| `namespace.yaml` | 命名空间 `xcmg-rca` |
| `configmap.yaml` | 应用配置 |
| `secret.example.yaml` | 密钥示例（生产环境需替换） |
| `deployment-api.yaml` | API 服务 Deployment |
| `deployment-worker.yaml` | Worker 服务 Deployment |
| `service.yaml` | ClusterIP Service |
| `ingress.yaml` | Ingress 路由 |
| `postgres-statefulset.yaml` | PostgreSQL StatefulSet |
| `redis-deployment.yaml` | Redis Deployment |
| `hpa.yaml` | 水平自动伸缩 |

部署命令：

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.example.yaml
kubectl apply -f k8s/redis-deployment.yaml
kubectl apply -f k8s/postgres-statefulset.yaml
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
```

## 项目结构

```
XCMG-MFG-RCA-Agent/
├── README.md
├── pyproject.toml
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── k8s/                          # Kubernetes 部署清单
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI 应用入口
│   ├── config.py                 # 配置管理
│   ├── api/
│   │   └── routes.py             # API 路由
│   ├── agent/
│   │   ├── state.py              # RCAState 定义
│   │   ├── workflow.py           # RCAWorkflow 编排器
│   │   └── nodes/                # 8 个工作流节点
│   ├── tools/                    # MCP 风格工具
│   ├── skills/                   # Skills SOP 定义
│   │   └── definitions/          # 6 个 YAML 技能文件
│   ├── rag/                      # RAG 混合检索
│   ├── text2sql/                 # Text2SQL 安全查询
│   ├── persistence/              # PostgreSQL 持久化
│   ├── schemas/                  # Pydantic 数据模型
│   ├── data/                     # 示例数据和知识文档
│   ├── scripts/                  # 工具脚本
│   └── tests/                    # 测试
```

## 面试边界说明

本项目为**开源演示版本**，用于展示架构设计和技术能力：

- ✅ **真实实现**：8 节点工作流、MCP 工具、RAG、Text2SQL、PostgreSQL 持久化、K8s 部署
- ✅ **示例数据**：使用 mock/sample 数据模拟 MES/APS/WMS/QMS 系统
- ✅ **大模型接入**：通过 OpenAI-compatible API 调用真实 LLM，并支持 Embedding 与 pgvector 向量检索
- ❌ **非生产就绪**：无真实系统集成、无认证鉴权、无异步任务队列
- 🔜 **生产扩展**：对接真实系统 API、Celery 异步池、多租户与企业认证

## License

MIT License
