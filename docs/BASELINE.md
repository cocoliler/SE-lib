# FlowStudio 设计基线 v3.1
更新：2026-11-15。状态：通用版设计已整理，待团队实现与实测。

正式名称：**FlowStudio — 通用可定制的智能软件工程工作流平台**（Configurable AI-Powered Software Engineering Workflow Platform）。
最终产品覆盖规格管理、规划、编排、执行、监督、验证与反馈。课堂作业 2 是首个纵向闭环：Design Spec → PM Agent → Task Decomposition → Orchestrator → Workflow Visualization。
不可将作业范围等同最终产品，也不可用固定产品任务表冒充通用规划。

## 权威来源
- 定位与范围：[产品定位](product/PRODUCT_POSITIONING.md)、[阶段边界](product/MVP_SCOPE.md)。
- 字段、状态和版本：[工作流契约](architecture/WORKFLOW_DATA_MODEL.md)、[规格模型](architecture/DESIGN_SPEC_MODEL.md)。
- 接口：[API](architecture/API_SPECIFICATION.md)；存储：[数据库](architecture/DATABASE_DESIGN.md)。
- 要求及验收：[SRS](product/REQUIREMENTS.md)、[追踪矩阵](product/REQUIREMENTS_TRACEABILITY.md)。
- 后续运行机制：[扩展架构](architecture/SE_WORKFLOW_EXTENSION.md)。运行专篇统一为 P2，不能覆盖当前计划契约。
- 完整目录：[文档入口](README.md)。旧 archive 内容仅为历史，不参与当前规范。

## 本次统一决策
1. 保留 Windows 本地单体、React/TypeScript/Vite/React Flow 和已有画布能力。
2. 作业 2 用 FastAPI + 独立 PM Agent + 纯函数编排器 + SQLite/SQLAlchemy；REST 轮询规划状态。LangGraph、SSE 为 P2 候选，非当前依赖。
3. 保留 SpecRevision、PlanRevision 名称，分别对应 DesignSpecVersion、WorkflowVersion；不创建同义实体双写。
4. Task 使用 task_id/name/dependencies 等统一字段；assigned_role 是建议角色，不代表运行中的 Agent。
5. PlanningRun 是一次模型规划请求；Run 是后续开发任务执行实例。两者绝不共用状态。
6. 已保存修订不可变；修改产生新修订；画布布局独立。依赖是唯一关系事实源，edges/batches/order 由服务端派生。
7. P0/P1/P2 在全目录分别指作业必需、作业体验增强、最终项目扩展；最终项目内部先后次序用 Phase 7–9 表达。
8. 各项性能、模型质量和 Windows 后端兼容性仍待实现验证，不把目标写成实测能力。

本轮范围补充：按用户最新要求先完成通用设计，不补具体产品案例或预设模板。PlanningPolicy为可选约束值对象，默认省略即可规划，未来模板仅作扩展适配器。
