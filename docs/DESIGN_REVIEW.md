# 设计审计
2026-11-14，自审完成；结论：可进入设计评审，尚不能称为已验证可运行产品。

| 检查 | 设计结论与依据 |
|---|---|
| 真正多Agent | Planner生成图，Worker真实模型/工具循环，Reviewer审查；验收A01/A05/A07 |
| 不退回传统流程 | 任务拓扑与修订由模型提议，程序只约束合法性与执行；不是固定九类规则节点 |
| 可执行计划 | 严格TaskSpec、DAG及引用校验，画布只投影 |
| 结果实际使用 | input_bindings+artifact hash，handoff ack可审计 |
| 有限终止 | 步数/时间/调用/token/修订全部有上限，恢复不清零 |
| 失败处理 | FAILED/BLOCKED区分，独立分支保留，未知副作用不重发 |
| 人工编辑 | 草稿CAS与运行不可变快照，批准绑定hash |
| 动态持久化 | revision追加，旧attempt/artifact不可变 |
| 图形与运行一致 | task_id映射与三类关系校验；layout不控制执行 |
| Windows | 单进程后端+静态前端；启动方案已设计但未实测 |
| 复杂度 | 不引入第二Agent框架、不引入分布式组件 |
| 可复现验收 | TEST与REAL分开，证据协议和故障窗口明确；均未执行 |

已修正的严重问题：旧基线将LLM列P2且禁自动拆解→本版提升为P0；原重启一律中断→改为checkpoint/operation对账与有条件恢复；动态修订与不可变历史冲突→revision追加；普通依赖冒充handoff→要求显式所有权转移与ack；跨库事务误判→稳定operation键与重入复用；P1重规划与演示修订冲突→P0限定审查修复，P1泛化。

待验证风险：LangGraph锁定版本的Send合流和SQLite异步saver兼容；主图版本升级时恢复迁移；DeepSeek能力/usage；Windows凭据存储与路径链接边界；100节点性能。M0先验证前三项，不通过需修改方案后开发。没有用户参考截图，视觉方向待评审。真实API验收仅在实施阶段做，本次没有Key也没有已实现引擎，不提供虚假的调用成功记录。

审查入口顺序：REFERENCE_PROJECTS→BASELINE→SYSTEM_ARCHITECTURE→ORCHESTRATION_ENGINE→STATE_MANAGEMENT→UI_UX_DESIGN→ACCEPTANCE_TESTS。审查通过后按T01开始；任何决策变更同时更新契约、状态、任务及验收。
