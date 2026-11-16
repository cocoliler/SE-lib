# 当前实现审计与迁移

更新于 2026-11-16。当前版本连接了浏览器工作台、规划服务、确定性编排与计划版本存储。

| 范围 | 当前实现 |
|---|---|
| 契约 | [Pydantic 模型](../tech/flowstudio_contracts/)定义 JSON Schema、OpenAPI、样例和前端 TypeScript 类型。 |
| 浏览器工作台 | [前端页面](../frontend/src/main.tsx)包含可折叠左栏、规格、任务与本地历史，支持 JSON 导入导出、项目删除和快照管理。 |
| PM Agent | [默认引擎](../backend/app/providers/default.py)将 REAL 交给 DeepSeek，TEST 使用显式 fixture。模型结果经结构和图校验，可在共享期限与 Token 预算内修复。无密钥的 REAL 请求返回 `MODEL_AUTH`。 |
| 校验与编排 | [服务端编排器](../backend/flowstudio_orchestration/)校验引用、需求覆盖和环，计算依赖、阶段及并行批次。浏览器也支持本地草稿预检和编排。 |
| 服务端保存 | [后端工作区](../frontend/src/backend-panel.tsx)使用 [HTTP 客户端](../frontend/src/api/client.ts)管理规格、规划运行、计划版本和布局。正式保存记录规划来源和已确认假设；布局独立更新，完整导出使用 ExportBundle。 |
| 画布 | [React Flow 画布](../frontend/src/canvas.tsx)支持搜索定位、拖动、连线、平移、缩放、注释和 PNG。 |
| 实际执行 | 当前产物是供团队审核和执行的任务计划；自动执行、工件检查与监督属于后续范围。 |

浏览器存储与服务端版本独立。已有 `flowstudio.workspace.v1` 中的旧注释坐标仍可读取，下一次保存使用平铺的 `x/y`。旧 CLI 在独立分支，其存储迁移需另行评估。

验证入口见[前端说明](../frontend/README.md)和[部署说明](development/LOCAL_DEPLOYMENT.md)。浏览器联调使用固定样例覆盖端到端保存流程，模型回归使用模拟提供商覆盖真实模式及图修复，避免验收依赖密钥和外部服务。
