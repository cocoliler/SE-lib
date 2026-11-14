# FlowStudio 多 Agent 设计基线 v2
2026-11-14；设计待评审，尚未实现。旧方案完整保留在 archive/workflow-v1，全部退出当前规范；历史资料不是本版依据。当前目录不是 Git 仓库。本轮不初始化仓库、不安装应用、不调用付费模型。

推荐模式 C：Planner + 确定性 Orchestrator + Workers + Reviewer；Coordinator 只能提交建议。React/TypeScript/Vite/React Flow/Tailwind/shadcn；Python/FastAPI/LangGraph，LangChain 仅用于模型与工具适配；SQLAlchemy + SQLite 业务库，独立 SQLite Checkpointer。HTTP 命令 + SSE。单后端进程，禁止多 uvicorn worker；不需要 Docker、Redis、消息队列或云。

统一对象：AgentVersion、PlanRevision、Run、TaskRun、Attempt、Artifact、Message、Event、Approval、ToolOperation。UUID 字符串，UTC RFC3339 时间，snake_case 字段。任务图是 DAG；修订产生新版本而非回边。画布 layout 不参与执行。所有运行冻结模型配置（不含密钥）、Agent 版本、计划与验收条件。

Run 状态：CREATED/PLANNING/READY/RUNNING/WAITING_HUMAN/REVIEWING/REVISING/COMPLETED/FAILED/CANCELED；调度暂停是独立 scheduling_paused 标志。TaskRun：PENDING/READY/RUNNING/WAITING_HUMAN/REVIEWING/COMPLETED/FAILED/BLOCKED/SKIPPED/CANCELED/INTERRUPTED。Attempt 单独留痕，不覆盖历史。

默认上限（设计值，未实测）：100任务/200依赖边；单run并发2，全局4，活动run2；Agent最多8次模型迭代；模型请求60秒、任务300秒；瞬时错误最多3次总尝试；规划格式修复2次；局部重规划2次；审查修订2次，均计入run累计预算，恢复不重置；run最多60次模型请求、100000 token、30分钟主动执行时间。人工等待24小时到期失败，不占执行槽。限制可下调；上调需要用户显式配置。预算不足在调用前阻止，未知usage标记unknown，不记零。

P0包括真实Agent闭环、基础并发、一次受限审查修订；P1扩大为通用局部重规划与并行优化。P0没有任意Shell、不受限写文件、RAG、云服务、多租户或实时协同编辑。无Key仅TEST模拟模式，不能作为真实模型验收。
