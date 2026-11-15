# 当前实现审计与迁移
审计日期2026-11-15；本地main最近提交99c77bd。本轮读取实际文件及Git跟踪列表；未运行前端浏览器或REAL模型。
此前的 v3 调整已整合为 v3.1，优先描述通用规划闭环。

| 证据 | 当前实现 | 通用设计差异 / 处置 |
|---|---|---|
| frontend/src/plan.ts | Task只有id/title/depends_on；固定两任务examplePlan；前端防环 | 增TaskProposal/详情/服务端权威校验；固定示例仍标TEST |
| frontend/src/main.tsx、canvas-tools.ts | 画布与需求输入、注释、手形、布局、PNG、本地草稿 | 保留交互资产；规格结构化与计划版本尚缺 |
| frontend/package.json | React/TS/Vite/@xyflow/react；build脚本 | 保留依赖；不为设计重写UI栈 |
| git ls-files frontend prototype | main跟踪frontend，未跟踪可用prototype源码；本地prototype只有缓存 | 不能把CLI历史分支当main网页后端 |
| main无backend | 尚无网页PM、编排API、SQLite业务模型 | T01契约→T02数据→T04/T05→T07整合 |
| v3旧设计 | 固定LangGraph主图、多Agent运行、SSE为首期；输入绑定规则有直接/祖先两种表述 | 当前纯规划，执行P2；统一直接依赖；新修订创建新Run |
| 当前用户要求 | 先写通用设计，不补案例和模板 | 本轮撤下新增样例；不建立模板库或强制选模板 |

迁移保留旧localStorage原文，不默认判有效；新增字段需补全，适配不改变原文件。
后端用新数据库路径/迁移版本；CLI库只作历史证据，不直接升级为新业务库。
