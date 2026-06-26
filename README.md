# XCMG Manufacturing RCA Agent

> 制造业根因分析智能体 — 基于官方 LangGraph 工作流的开源项目

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-1C3C3C?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![Pydantic](https://img.shields.io/badge/Pydantic-2.5+-E92063?style=flat-square&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI--compatible-API-412991?style=flat-square&logo=openai&logoColor=white)](https://platform.openai.com/docs/api-reference)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

## 项目概述

XCMG-MFG-RCA-Agent 是一个面向制造业的根因分析（Root Cause Analysis）智能体系统。它采用 **官方 LangGraph 有向图工作流**，结合 **MCP 风格工具调用**、**Skills SOP 知识库**、**RAG 混合检索** 和 **Text2SQL 安全查询**，自动分析 MES/APS/WMS/QMS 系统中的生产异常事件，定位根因并生成分析报告。

### 核心特性

- **8 节点 RCA 工作流**：`analyze_symptom → generate_hypotheses → select_tool → execute_tool → observe_evidence → draft_rca → reflect → generate_report`，支持反思循环
- **MCP 风格工具系统**：8 个工具（工单查询、资源调度、设备维保、物料库存、接口日志、质量记录、知识检索、Text2SQL）
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
| 工作流 | 8 节点官方 LangGraph RCA 工作流 | ✅ |
| 工作流 | 反思循环（最多 3 轮） | ✅ |
| 工具 | 8 个 MCP 风格工具（工单/资源/设备维保/物料/接口/质量/知识/Text2SQL） | ✅ |
| 工具 | 工具注册中心（单例模式） | ✅ |
| Skills | 6 种异常类型 YAML SOP 定义 | ✅ |
| RAG | 混合检索（关键词 + Embedding 向量 + Reranker 重排序） | ✅ |
| RAG | Markdown 知识文档加载和分块 | ✅ |
| LLM | 接入大语言模型增强假设生成和报告质量 | ✅ |
| pgvector | 使用 PostgreSQL/pgvector 保存知识库 Embedding 向量 | ✅ |
| Text2SQL | 模板驱动 SQL 生成 | ✅ |
| Text2SQL | 安全验证（只读 SELECT + 白名单 + LIMIT） | ✅ |
| Text2SQL | PostgreSQL 执行器 | ✅ |
| 持久化 | PostgreSQL 任务/报告/检查点/去重表 | ✅ |
| 持久化 | 检查点保存和恢复 | ✅ |
| API | FastAPI 6 个端点（health/analyze/reports/tasks/events/chat） | ✅ |
| 部署 | Dockerfile + docker-compose.yml | ✅ |
| 部署 | K8s manifests（Deployment/Service/Ingress/HPA/ConfigMap） | ✅ |
| 数据 | 示例 MES/APS/WMS/QMS 数据 | ✅ |
| 测试 | pytest 单元测试、集成测试与冒烟测试 | ✅ |

## 计划功能

以下功能为生产环境扩展预留：

| 功能 | 说明 |
|------|------|
| Worker 异步池 | 将 RCA 任务从同步执行改为 Celery/Redis 异步任务队列 |
| SSO/JWT 认证 | 集成企业单点登录和 JWT Token 鉴权 |
| 真实系统集成 | 对接实际 MES/APS/WMS/QMS 系统 API |
| 多租户 | 支持多工厂/多组织隔离 |
| 趋势分析 | 基于历史 RCA 数据的根因趋势和模式挖掘 |
| 实时监控 | WebSocket 推送工作流执行状态 |

## 快速开始

### 环境要求

- Python 3.10+
- pip
- 外部 PostgreSQL 14+（需安装 pgvector 扩展）

### 1. 安装依赖

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
python -m pip install -e ".[dev]"
```

项目依赖统一维护在 `pyproject.toml` 中，`python -m pip install -e .` 会自动同步安装 `[project] dependencies` 中声明的所有运行时依赖；`python -m pip install -e ".[dev]"` 会额外安装 pytest 等测试依赖。

### 2. 配置 PostgreSQL 与大模型

复制 `.env.example` 为 `.env`，至少配置：

```env
DATABASE_URL=postgresql://rca_user:rca_password@localhost:5432/xcmg_rca
DATABASE_SCHEMA=rca
BUSINESS_DATABASE_URL=postgresql://rca_user:rca_password@localhost:5432/xcmg_rca
BUSINESS_DATABASE_SCHEMA=public
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
psql "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca" -f db/003_init_metadata_seed.sql
psql "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca" -f db/004_init_vector_schema.sql
```

其中：

- `db/001_init_app_schema.sql` 创建 RCA 应用表（任务、报告、反馈、检查点、聊天）和元数据层表（数据源、表结构、字段含义、业务术语等）。
- `db/002_init_business_schema.sql` 创建示例业务表（工单、设备维保、物料库存、质量记录、接口日志），仅用于本地开发/演示。
- `db/003_init_metadata_seed.sql` 插入元数据初始数据（数据源、字段映射、业务术语、关联关系、指标定义、查询模板）。
- `db/004_init_vector_schema.sql` 启用 `pgvector` 扩展并创建向量表（时间戳默认值已统一为日期零点精度）。

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
  "status": "pending",
  "events_url": "/api/v1/rca/events/rca-a1b2c3d4e5f6"
}
```

### SSE 流式事件

```bash
curl http://localhost:8000/api/v1/rca/events/rca-a1b2c3d4e5f6
```

服务端以 `text/event-stream` 格式推送工作流状态、工具执行和反思循环的实时事件。

### 聊天交互

```bash
curl -X POST http://localhost:8000/api/v1/rca/chat \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "rca-a1b2c3d4e5f6",
    "message": "为什么根因是物料短缺？"
  }'
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

Docker Compose 配置位于 `deploy/docker/docker-compose.yml`，当前只部署 `api` 服务；PostgreSQL、LLM、Embedding 和 Reranker 均使用外部服务。部署前先复制 `.env.example` 为 `.env`，并按实际环境修改参数。

关键配置：

- `API_PORT`：宿主机暴露端口，默认 `8000`。
- `DATABASE_URL` / `DATABASE_SCHEMA`：RCA 任务、报告、检查点等应用数据存储。
- `BUSINESS_DATABASE_URL` / `BUSINESS_DATABASE_SCHEMA`：Text2SQL 和业务工具查询的业务库。
- `VECTOR_DB_PROVIDER` / `VECTOR_DATABASE_URL` / `VECTOR_DB_SCHEMA` / `VECTOR_TABLE_NAME`：知识库向量存储，默认使用 `pgvector`。
- `RAG_SOURCE_DIR` / `RAG_CHUNKS_DIR` / `RAG_INDEX_MODE`：知识文档来源、人工确认分块目录和索引模式。
- `LLM_*`、`EMBEDDING_*`、`RERANKER_*`：分别配置大模型、向量模型和重排序模型。

示例：

```env
API_PORT=8000

DATABASE_URL=postgresql://rca_user:rca_password@postgres.example.com:5432/xcmg_rca
DATABASE_SCHEMA=rca
BUSINESS_DATABASE_URL=postgresql://rca_user:rca_password@postgres.example.com:5432/xcmg_rca
BUSINESS_DATABASE_SCHEMA=public

VECTOR_DB_PROVIDER=pgvector
VECTOR_DATABASE_URL=postgresql://rca_user:rca_password@postgres.example.com:5432/xcmg_rca
VECTOR_DB_SCHEMA=rca_vector
VECTOR_TABLE_NAME=knowledge_embeddings

RAG_SOURCE_DIR=./app/data/knowledge/raw
RAG_CHUNKS_DIR=./app/data/knowledge/chunks
RAG_INDEX_MODE=manual
RAG_CHUNK_FILE_PATTERN=**/*.jsonl

LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-key-here
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=3

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=bge-m3
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_API_KEY=
EMBEDDING_DIMENSION=1024
EMBEDDING_BATCH_SIZE=32

RERANKER_PROVIDER=ollama
RERANKER_MODEL=dengcao/Qwen3-Reranker-4B:Q4_K_M
RERANKER_BASE_URL=http://localhost:11434
RERANKER_API_KEY=ollama
RERANKER_TOP_N=5
```

从仓库根目录启动：

```bash
docker compose --env-file .env -f deploy/docker/docker-compose.yml up -d --build
```

或进入 `deploy/docker` 目录启动：

```bash
docker compose --env-file ../../.env up -d --build
```

健康检查：

```bash
curl http://localhost:8000/api/v1/rca/health
```

## K8s 部署

`deploy/k8s/` 目录包含完整的 Kubernetes 部署清单：

| 文件 | 说明 |
|------|------|
| `namespace.yaml` | 命名空间 `xcmg-rca` |
| `configmap.yaml` | 应用配置 |
| `secret.example.yaml` | 密钥示例（生产环境需替换） |
| `deployment-api.yaml` | API 服务 Deployment |
| `deployment-worker.yaml` | Worker 服务 Deployment（占位/预留） |
| `service.yaml` | ClusterIP Service |
| `ingress.yaml` | Ingress 路由 |
| `postgres-statefulset.yaml` | PostgreSQL StatefulSet |
| `redis-deployment.yaml` | Redis Deployment |
| `hpa.yaml` | 水平自动伸缩 |

部署命令：

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.example.yaml
kubectl apply -f deploy/k8s/redis-deployment.yaml
kubectl apply -f deploy/k8s/postgres-statefulset.yaml
kubectl apply -f deploy/k8s/deployment-api.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
kubectl apply -f deploy/k8s/hpa.yaml
```

## 项目结构

```
xcmg-mfg-rca-agent/
├── README.md                      # 项目说明文档
├── pyproject.toml                 # 项目元数据与依赖声明
├── uv.lock                        # uv 依赖锁文件
├── .env.example                   # 环境变量模板
├── .dockerignore                  # Docker 构建忽略规则
├── .gitignore                     # Git 忽略规则
├── app/                           # 应用主代码
│   ├── main.py                    # FastAPI 应用入口
│   ├── config.py                  # 配置管理
│   ├── api/                       # API 路由与聊天执行逻辑
│   │   ├── routes.py              # RCA 分析 REST 接口
│   │   ├── chat_routes.py         # 聊天 REST 接口
│   │   └── chat_execute.py        # 聊天执行逻辑
│   ├── agent/                     # RCA 工作流引擎
│   │   ├── state.py               # RCAState 状态定义
│   │   ├── node_adapter.py        # 节点适配器（兼容 LangGraph 状态）
│   │   ├── workflow.py            # RCAWorkflow 编排器（官方 LangGraph 编排）
│   │   └── nodes/                 # 8 个工作流节点
│   ├── tools/                     # MCP 风格工具系统
│   ├── skills/                    # Skills SOP 知识库
│   │   └── definitions/           # 6 种异常类型 YAML SOP
│   ├── rag/                       # RAG 混合检索、Embedding、pgvector、Reranker
│   ├── text2sql/                  # Text2SQL 生成、验证与执行
│   ├── llm/                       # OpenAI-compatible LLM 客户端
│   ├── prompts/                   # 提示词模板与 YAML 定义
│   ├── persistence/               # PostgreSQL 持久化、检查点、聊天仓储
│   ├── schemas/                   # Pydantic 请求/响应与业务模型
│   ├── data/                      # 应用内示例数据与知识文档
│   ├── scripts/                   # 初始化、演示、冒烟测试和向量入库脚本
│   └── tests/                     # 单元测试与集成测试
├── db/                            # 数据库初始化 SQL 脚本
├── deploy/                        # 容器化部署配置
│   ├── docker/                    # Dockerfile、Compose 模板与部署脚本
│   └── k8s/                       # Kubernetes 部署清单
├── static/                        # 前端聊天 UI 静态资源
└── scripts/                       # 根目录辅助脚本
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
