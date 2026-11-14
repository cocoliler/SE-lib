# 技术选型

| 采用或评估 | 理由 |
|---|---|
| React + TypeScript + Vite + React Flow | main 已可构建。沿用已有 CSS，Tailwind 和 shadcn/ui 待组件复用需要时评估 |
| Python + FastAPI + Pydantic | 接续 Python 原型，提供共享契约、校验和 HTTP/SSE |
| LangGraph 固定主图 | 并行和汇聚用 Send/reducer，业务调度与状态由确定性规则控制，详见[取舍](ORCHESTRATION_ENGINE.md) |
| LangChain 可选 | 模型适配器隔离供应商。若原生接口已满足 JSON 与用量信息，可不引入完整依赖 |
| DeepSeek | REAL 可配置模型连接，TEST 使用独立适配器。严格校验模型返回 |
| SQLite + SQLAlchemy + Alembic | 单机事务和持久化，版本化业务表设计 |
| SQLite Checkpointer 后置 | 首版同进程人工确认，持久业务数据先满足审计。跨重启续跑要处理版本、幂等、副作用和断点对账 |
| SSE | 单向事件，控制命令用 HTTP；阶段性轮询辅助联调。不引入 WebSocket 双向会话管理 |

参考证据见[研究报告](../research/REFERENCE_PROJECTS.md)。依赖版本与 Windows 支持需 Phase 2 实测锁定，正式后端当前未实现。
