# 当前实现审计与迁移

审计日期 2026-11-15。此次集成以包含 `tech/` 契约模块的 `16fb5da` 为主分支基线，前端实现取自 `codex/b/T06-workflow` 的 `1415ffe`。以下说明覆盖集成后的工作区能力。

| 范围 | 现有实现与证据 | 联调缺口 |
|---|---|---|
| 统一契约 T01 | [Pydantic 模型](../tech/flowstudio_contracts/)生成 JSON Schema、OpenAPI、样例和 TypeScript；前端分支消费 Schema 与生成类型。 | 生成的 TypeScript 文件曾被删除，本次集成恢复了清单对应的文件。后续修改契约时同步生成并检查漂移。 |
| 浏览器工作区 T03/T06 | [页面与导航](../frontend/src/main.tsx)、[表单](../frontend/src/forms.tsx)及[导入预览](../frontend/src/workspace-panels.tsx)支持空项目、规格编辑、任务和依赖编辑、JSON 预览与导入/导出。业务来源显示 MANUAL、IMPORTED 或 PRESET。 | PM Agent 服务仍未接入。会议室预约为用户显式选择的 PRESET；契约样例用于测试与将来显式 TEST。 |
| 本地试排 | [前端校验与编排](../frontend/src/plan.ts)实现引用、环、100 任务 / 1,000 边上限、需求覆盖、关键假设和跨任务假设 ID 检查；导入拒绝重复 JSON 键。must 缺覆盖阻断，should/could 缺覆盖提示警告。 | 浏览器报告用于草稿预检；服务端在保存时重算同一套规则，见下行。引用覆盖不能证明交付实质满足需求。 |
| 服务端编排 T05 | [确定性编排器](../backend/flowstudio_orchestration/)实现结构/引用/覆盖校验、Kahn 批次、阶段分组与迭代式环定位；报告绑定 input_hash 与 rules_version。53 项 unittest 通过，官方样例的边/阶段/批次/顺序一致，100 任务/1000 边 p95≈3.9ms（Linux，Python 3.12）。 | Windows 基准未实测；可选需求覆盖告警与边数上限两处契约缺码见[校验协议](architecture/WORKFLOW_VALIDATION.md)。 |
| 规划闭环后端 T02/T07 | [FastAPI 入口](../backend/app/main.py)、[计划用例](../backend/app/application/plan_service.py)、[仓储](../backend/app/persistence/repos.py)与 Alembic 迁移已实现 18 个契约操作：规格版本 CAS、规划队列与恢复、计划保存/追加、布局 CAS、ExportBundle、幂等命令。DTO 全部来自 `tech/flowstudio_contracts`，编排直接调用 T05；`backend/tools/export_openapi.py` 做契约漂移检查。pytest 118 项、unittest 53 项通过。 | 真实 PM Agent（T04）未接入：REAL 请求以 MODEL_AUTH 失败，TEST 需显式 fixture；模型质量、费用与重试预算待 C 验证。 |
| 画布 | [React Flow 画布](../frontend/src/canvas.tsx)支持任务搜索定位、拖动、连线、手形平移、缩放、PNG、卡内编辑注释。自动布局只移动任务。 | 前端尚未切换到服务端 Layout/PUT 接口；契约的 notes 是 CanvasNote 数组，接入时需把本地注释映射为 id/text/x/y/color?。 |
| 本地保存和历史 | [存储](../frontend/src/storage.ts)保存草稿与最多 30 个只读快照；[布局转换](../frontend/src/layout.ts)读取旧嵌套坐标并保存为平铺 x/y。 | 服务端版本、CAS/409、ExportBundle 已可用；前端仍走本地快照，切换后需处理 409 与只读历史。 |
| PM 与实际执行 | 规划 Provider 端口与默认分发已落地：TEST 读 fixture，REAL 明确失败并保留诊断。 | 真实 Provider、模型质量与费用、工具执行、审查和恢复均待验证。 |

## 迁移与验收

- 当前浏览器工作区使用 `flowstudio.workspace.v1`。已有该存储键下的嵌套注释坐标可加载，下次保存改用 x/y。历史 `flowstudio-t04-draft` 保持独立；如后续提供导入，先备份再映射字段，并重新校验来源和依赖。
- 本地快照用于记录编辑状态。接入正式版本时，从通过校验的候选构造 PlanRevision；布局另存，并在来源适配中保留真实规划运行的 REAL/TEST 来源。
- 本次文档核对以提交 `1415ffe` 的前端代码为基线，重新运行生产构建、17 项领域测试和 Chromium 端到端测试，均通过。覆盖官方样例、本地编排、导入校验、保存恢复、画布拖动与 PNG。运行入口见[前端说明](../frontend/README.md)，课堂验收见[验收标准](testing/ACCEPTANCE_TESTS.md)。
- 旧 CLI 原型在独立分支，当前分支的网页后端为 `backend/app`。后端已启用新数据库迁移流程，旧 CLI 存储如需迁移须单独评估。
