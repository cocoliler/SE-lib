# FlowStudio 设计基线 v3

当前设计调整待团队评审。正式定位见[产品定位](product/PRODUCT_POSITIONING.md)，交付边界以[首版范围](product/MVP_SCOPE.md)为准。当前实现与设计差异见[审计](PROJECT_AUDIT.md)。

统一采用 SpecRevision、PlanRevision、Run、TaskRun、Attempt、Artifact、Message、Event、Approval 和 ToolOperation。ID 使用 UUID，计划内有稳定 task_id，时间为 UTC RFC3339。业务规格和已确认快照不可变，画布坐标与注释单独保存。Run 与 TaskRun 状态以[状态管理](architecture/STATE_MANAGEMENT.md)为准。

Windows 本地单体：React/TS/Vite/React Flow，FastAPI、LangGraph 固定主图、SQLAlchemy/SQLite、SSE。LangChain 可用于模型适配。先串行联调，正式验收覆盖并行和一次审批修订。不导入通用权限系统或分布式基础设施。模型、预算与终止限额见[编排引擎](architecture/ORCHESTRATION_ENGINE.md)。旧规则工作流文档仅作历史资料。
