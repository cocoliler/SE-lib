# FlowStudio v3.1 前端

在 `frontend` 目录使用 Node.js 22.12 或更高版本。

```powershell
npm ci
npm run dev
npm run build
npm test
npm run test:browser
```

浏览器测试读取生产构建，运行前先执行 `npm run build`。它使用本机 Chrome、Chromium 或 Edge，也可用 `CHROME_BIN` 指定浏览器。测试使用独立的临时配置目录和本地端口。

## 使用流程

1. 创建空项目，填写 Design Spec，或导入符合规格 Schema 的 JSON 并确认预览。规格通过基础校验后可进入任务规划。也可在工作台选择「从示例创建」，打开内置的会议室预约项目。
2. 手动创建任务，或导入符合任务 Schema 的 TaskPlan JSON。界面持续显示 PM Agent 服务未连接，并区分导入、手动和内置预设来源。
3. 在任务详情或画布里设置依赖。补齐任务字段后选择「重新编排」，查看并行批次。任务或规格修改后需要重新编排。
4. 在工作流画布中可拖动节点、切换选择与平移、在画布上放置注释、自动布局并导出 PNG。任务列表与节点共用同一任务数据。
5. 「保存到浏览器」保存当前改动。「保存快照」同时记录该项目的规格、任务、来源和画布布局，保留最近 30 个只读快照。

## JSON 与存储

- [Design Spec Schema](../docs/contracts/design-spec.schema.json) 定义规格 JSON。
- [TaskProposal Schema](../docs/contracts/task-proposal.schema.json) 定义本地 TaskPlan 的可交换内容。导入会先检查结构，依赖问题可在预览中查看并在应用后修正。项目内的来源、快照和画布布局保存在浏览器本地。
- Draft 与本地历史使用 `flowstudio.workspace.v1`。旧示例草稿的存储键保持原样，新工作区从空白开始。
- `PlanningProvider` 是后续接入的 TypeScript 边界。页面目前通过手动录入和 JSON 文件获得任务数据。
