# 参考项目研究与选型

## 本轮复核与采用边界

- Dify 的[画布源码](https://github.com/langgenius/dify/blob/main/web/app/components/workflow/index.tsx)和[运行历史](https://docs.dify.ai/en/use-dify/debug/history-and-logs)支持从图到节点调试的布局思路。FlowStudio 保留按需详情与运行证据。
- n8n 官方[执行分类](https://docs.n8n.io/workflows/executions/)区分不同执行入口。FlowStudio 让草稿、快照与运行历史可辨认。
- Flowise [Agentflow V2](https://docs.flowiseai.com/using-flowise/agentflowv2)体现工具授权及人工节点。FlowStudio 首版权限固定，等待点与实际业务审批绑定。
- LangGraph [Send](https://docs.langchain.com/oss/python/langgraph/graph-api#send)支持逐任务并行参数和 reducer。[Interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts)恢复会重新进入节点。固定主图选型及启动恢复限制据此落在编排与状态文档。
- CrewAI [Tasks](https://docs.crewai.com/en/concepts/tasks)提供输出 guardrail 与有界重试。FlowStudio 采用确定性检查与模型审查分层。
- React Flow [自定义节点](https://reactflow.dev/learn/customization/custom-nodes)支持布局和展示组件。业务图与前端布局隔离。

以下为 v2 研究及历史取舍。交付范围与运行承诺以新版[基线](../BASELINE.md)为准。
研究日期2026-11-14。实际访问下列官方文档与仓库页面；未安装运行参考项目、未逐行审计内部源码、未固定提交版本。以下“确认”限于公开接口和文档，所有本项目适配策略是设计建议。实施前锁定兼容依赖并做Windows实验。

| 项目 | 已确认设计及来源 | FlowStudio采用的建议与边界 |
|---|---|---|
| LangGraph | [仓库](https://github.com/langchain-ai/langgraph)；[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)提供StateGraph、状态更新/reducer、条件路由和Send并行 | 固定主控制图读取动态计划；并行结果以task/attempt键合并，避免覆盖；不把React节点直接反射为Python代码 |
| 持久化/人工 | [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)描述checkpoint、thread与resume；中断节点恢复会重新进入 | 同run使用稳定thread_id；副作用单独封装并去重，checkpoint不等于外部操作事务 |
| Supervisor/handoff | [Subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)描述主管调用子Agent与上下文隔离；[Handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)通过状态切换活动Agent | 借鉴角色协调和受限交接；不允许Agent直接改变运行库 |
| CrewAI | [仓库](https://github.com/crewAIInc/crewAI)、[Flows](https://docs.crewai.com/en/concepts/flows)、[Tasks](https://docs.crewai.com/en/concepts/tasks)、[Processes](https://docs.crewai.com/en/concepts/processes)：Flow管理流程/状态，Crew组织角色任务，层级过程包含管理者，任务支持结构化输出与校验 | 采用role/goal/expected_output和guardrail思想；不同时嵌入第二套执行运行时；主观管理者验收仍需程序验证 |
| Microsoft Agent Framework | [概览](https://learn.microsoft.com/agent-framework/overview)、[Workflows](https://learn.microsoft.com/en-us/agent-framework/journey/workflows)：Agent的模型决策与显式workflow控制区分，提供顺序、并行、handoff等模式 | 借鉴类型化消息、执行边界与人工干预；本期不增加另一SDK和服务体系 |
| Dify | [运行历史](https://docs.dify.ai/en/use-dify/debug/history-and-logs)提供历史执行与排错入口 | 采用运行抽屉与节点输入输出查看；不移植部署拓扑 |
| n8n | [执行](https://docs.n8n.io/workflows/executions/)区分运行并提供执行查询 | 草稿测试/真实运行显式分离；失败定位链接到attempt |
| Flowise | [Agentflow V2](https://docs.flowiseai.com/using-flowise/agentflowv2)介绍Flow State及多Agent节点 | 参考Agent画布与状态展示；共享状态仅引用授权artifact |
| React Flow | [自定义节点](https://reactflow.dev/learn/customization/custom-nodes)、[保存恢复](https://reactflow.dev/examples/interaction/save-and-restore)支持自定义节点组件及图形状态保存 | handles分类型、layout单独存储；撤销、业务校验和自动布局需应用实现，不宣称组件自带全部业务能力 |
| DeepSeek | [JSON输出](https://api-docs.deepseek.com/guides/json_mode/)说明JSON模式配置 | JSON合法不等于符合业务Schema；后端仍严格解析、校验与有限修复 |

## 三种协作模式比较（本项目工程判断）
| 模式 | 扩展性 | 可靠性/状态 | 成本 | 可视化 |
|---|---|---|---|---|
| A Supervisor | 角色增加容易，主管上下文与调用瓶颈 | 集中会话易管理，但每步模型路由需约束 | 初期低，长期调试中 | 树形容易，动态历史需记录 |
| B Swarm | 专家直接交接灵活 | 所有权、循环与恢复复杂 | 高 | 静态图难预测，实际轨迹必须独立 |
| C Planner+编排器 | 图任务可并行、模块职责明确 | 状态机可验证，计划失败可拦截 | 初期中 | 计划、执行、修订一一追踪 |

推荐C吸收A；B仅以白名单handoff实现，不作为全局运行模式。另一架构备选为每次计划编译一个StateGraph：直观但动态修订、图版本和恢复耦合更强；推荐固定主图+数据化DAG，避免每次恢复重构任意拓扑。单体进程优于独立worker：本期I/O并发足够，后者增加IPC与租约管理；若CPU工具出现阻塞，再按测量隔离。
