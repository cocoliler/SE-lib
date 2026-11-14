# 可逐项交给Codex的任务

团队现调整为六人；下表任务编号与依赖保留，负责人分配由[六人分工](TEAM_ASSIGNMENTS.md)覆盖，原3～5人兼任方案不再采用。
前置：设计审查通过后才执行；每项独立PR，输入为v2文档，必须附测试与证据，不一次生成整个系统。

| ID/负责人 | 工作与交付 | 依赖 | 完成条件 |
|---|---|---|---|
| T01 后端A | Windows依赖矩阵与最小LangGraph实验 | 无 | 并行reducer/interrupt/SQLite重启通过，记录锁定版本 |
| T02 全栈B | Pydantic Plan/Agent/消息/API契约与TS生成 | T01 | 非法schema、循环、引用、未知字段测试拒绝 |
| T03 后端C | SQLite迁移、仓储、CAS、事件事务 | T02 | rollback/唯一约束/审批竞争测试 |
| T04 前端D | 画布节点/三类边/layout/撤销 | T02 | 保存往返与键盘E2E，无运行模拟冒充 |
| T05 后端A | 模型profile/凭据/预算/TEST适配 | T02,T03 | 真实接口探针、无Key明确测试、并发预算正确 |
| T06 后端B | Agent注册与版本/工具权限网关 | T03,T05 | 越权路径、HTTP重定向、超时被阻止 |
| T07 后端A | Planner结构化计划与修复 | T05,T06 | 2次修复上限、图合法后可编辑 |
| T08 后端C | 固定主图、Send派发、artifact/reducer | T03,T06 | 独立任务并行，依赖不提前执行 |
| T09 全栈D | SSE、历史抽屉、审批表单 | T03,T04,T08 | 断线补发、重复事件、409冲突测试 |
| T10 后端C | pause/cancel/restart与operation去重 | T08,T09 | 故障窗口和晚到结果测试 |
| T11 后端B | Reviewer、handoff、受限revision | T07,T08,T10 | 真交接ack与结构化审查、历史不可变 |
| T12 QA/E | 演示fixture、TEST故障矩阵、REAL证据包 | T09,T11 | 验收文档所有P0项有结果 |
| T13 全栈D | Windows启动/备份/日志脱敏 | T10,T12 | 新机器少量命令启动与恢复通过 |

3人时A兼C，B兼QA，D专前端；5人时按表分工。每次Codex任务写明目标、允许目录、依赖契约、验收命令与禁止扩范围。M0实验不得被包装成最终平台。审查不通过先修设计，避免多人各实现一套状态枚举。
