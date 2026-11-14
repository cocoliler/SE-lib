# 可独立开发的任务

任务所有者与里程碑见[开发路线图](ROADMAP.md)。每项一个可验收 PR，附命令与样例。T04 已有前端底座，以下补充为拟议工作。

| 任务 | 主要工作区 | 接口交付 |
|---|---|---|
| T01/T02 A、F | docs | 审计、设计评审决定、边界及风险 |
| T03 A、E | contracts、backend/app/persistence | Spec 与 Plan JSON、API 错误/事件样例、迁移 |
| T04 B | frontend | 规格表单、兼容旧草稿、候选编辑与确认 |
| T05 C | backend/app/agents、models | TEST/REAL 适配和角色 Schema |
| T08 D、E、C | backend/app/orchestration、persistence | 依赖并行、真实产物与失败传播 |
| T09 B、E | frontend、backend/app/api | 运行视图、快照、SSE |
| T10 D | backend/app/orchestration | 人工控制、取消、重启标记和幂等 |
| T11 C、D、B | agents、orchestration、frontend | 程序检查、审查、一次修订与验证视图 |
| T12/T13 F、E | tests、scripts | 选课 fixture、证据、Windows 启动 |

依赖和验收 ID 在路线图；交叉修改契约先同步生成件与 fixture。
