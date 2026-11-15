# 通用设计摘要
## 产品与本轮交付
FlowStudio：通用可定制的智能软件工程工作流平台。
最终面向规格管理、任务规划、编排、执行、监控、验证和反馈；课堂作业2只先落地：
**Design Spec → PM Agent → Task Decomposition → Orchestrator → Workflow Visualization**。
v3.1 交付通用规划流程的产品与技术设计。具体案例和预设模板留待后续评估。

## 核心设计
- 输入统一Design Spec，需求有稳定ID和验收条件；关键信息不足必须提示。
- PM根据实际规格给出任务、交付、依赖、建议角色和来源需求；结构化输出、预算和有限修复。
- 编排器纯程序完成唯一性/引用/环检查、Kahn拓扑分层及并行机会计算，复杂度O(V log V+E)。
- 同一任务数据投影列表和画布，人工修改重校验；坐标、注释不参与业务执行顺序。
- SpecRevision和PlanRevision不可变，PlanningRun与未来Run分开；保存采用CAS/幂等。
- 无预设模板也可规划；可选约束通过PlanningPolicy传入，未来模板只作为此接口的适配器。
- Windows本地单体，React/TS/Vite/React Flow，FastAPI/Pydantic/SQLite/SQLAlchemy，当前REST轮询。
- 保留现有前端，不为技术清单引入全量UI重写；LangGraph/SSE和多Agent实际执行为P2。

## 关键入口
总体/课堂流程图见 [架构](architecture/SYSTEM_ARCHITECTURE.md)。
需求和验收连接见 [追踪矩阵](product/REQUIREMENTS_TRACEABILITY.md)。
PM详解见 [PM设计](architecture/PM_AGENT_DESIGN.md)，算法见 [编排器](architecture/ORCHESTRATION_ENGINE.md)。
前端见 [UI/UX](design/UI_UX_DESIGN.md) 和 [画布](design/WORKFLOW_EDITOR.md)。
研究依据见 [研究报告](research/REFERENCE_PROJECTS.md)，风险见 [评审](DESIGN_REVIEW.md)。
下一阶段按 [任务](development/TASK_BREAKDOWN.md)：T01统一契约→T02/T03规格→T04 PM/T05编排→T06/T07图与版本→T08验收。
