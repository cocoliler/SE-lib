# 六人团队分工与 Git 交付

成员以 A～F 代称，实际姓名待团队自行对应。当前阶段交付设计，审查通过后才编码。

| 成员 | 职责 | 设计交付 | 实施任务与边界 |
|---|---|---|---|
| A 技术负责人 | 研究、架构基线、契约 | REFERENCE_PROJECTS、BASELINE、SYSTEM_ARCHITECTURE | T01、T02；负责兼容实验、Pydantic/OpenAPI与TS生成；审查跨模块变更 |
| B 前端负责人 | 产品、交互与编排画布 | PRD、UI_UX_DESIGN、WORKFLOW_EDITOR | T04与T09前端；画布、属性、审批、事件展示，不实现后端调度 |
| C Agent负责人 | 模型、角色、规划与审查 | MULTI_AGENT_ARCHITECTURE | T05、T06的Agent部分、T07、T11的Reviewer部分；输出建议与结构化产物，不直接改运行状态 |
| D 编排负责人 | 调度、通信、交接与状态恢复 | ORCHESTRATION_ENGINE、AGENT_COMMUNICATION、STATE_MANAGEMENT | T08、T10、T11的handoff与revision部分；状态转移和预算调度执行 |
| E 数据与平台负责人 | 数据库、工具网关、API与本地启动 | DATABASE_DESIGN；维护SYSTEM_ARCHITECTURE中的API/工具设计 | T03、T06工具部分、T09后端、T13；持久化、权限、SSE补发、Windows启动 |
| F 测试与交付负责人 | 测试、审计、路线图和协作流程 | ACCEPTANCE_TESTS、DESIGN_REVIEW、ROADMAP、TASK_BREAKDOWN、GIT_COLLABORATION | T12与持续验收；维护追踪矩阵和证据，不替其他成员补写功能测试 |

## 六部分设计提交

1. A：研究、统一基线与系统架构；包含历史设计归档、文档入口和.gitignore。
2. B：产品需求、UI/UX与可视化编辑器。
3. C：多Agent角色与模型协作体系。
4. D：编排引擎、通信协议与状态管理。
5. E：数据库设计。
6. F：开发路线、任务分解、Git规范、六人分工、验收与审计。

这里的六次提交用于组织现有设计，不表示每位成员已独立完成或签署这些成果。每次提交使用实际操作者身份，不伪造作者。

## 依赖与交接

A先冻结契约v1；B可据契约用明确TEST fixture开发画布，C验证模型结构化输出，E建立仓储。D依赖A契约与E事务接口实现主图。B/E依据同一SSE契约对接，C/D依据同一artifact与handoff契约对接。F从第一阶段提供验收案例，最终组织REAL验收；TEST不能代替REAL。

契约变更由A主审，受影响成员共同评审；SYSTEM_ARCHITECTURE由A维护，E通过单独PR修改API/工具章节，避免同时覆盖文件。每人负责本模块测试；F负责跨模块故障注入与验收证据。

## Git操作约定

main为集成分支；不建立六条长期个人分支。每人从最新main创建带负责人和任务号的短分支，例如feature/a/T02-contracts、feature/b/T04-canvas、feature/c/T07-planner、feature/d/T08-runtime、feature/e/T03-persistence、test/f/T12-acceptance。

典型流程：git switch main → git pull --ff-only → git switch -c <任务分支> → 修改与测试 → git add <明确文件> → git commit → git push -u origin <任务分支> → 创建PR。当前尚未配置远端时跳过pull/push；不得杜撰仓库地址。

一个任务可有多次小提交，一个PR只覆盖一个可验收目标；提交格式docs(scope):、feat(scope):、fix(scope):、test(scope):。代码作者不能自审合并；至少一位非作者批准，契约/状态/数据库变更需相关owner共同批准。设计审核通过之前，不开始T01之后的系统实施。
