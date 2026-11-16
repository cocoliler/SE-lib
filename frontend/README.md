# FlowStudio v3.1 前端

开发环境需要 Node.js 22.12+ 和 npm。后端、前端的启动命令和 DeepSeek 配置见 [Windows 本地开发与运行](../docs/development/LOCAL_DEPLOYMENT.md)。

## 工作台

- 左栏包含项目切换、新建项目和后端工作区。点项目工作台旁的折叠按钮可给右侧画布腾出空间。点选中项目那一行的「×」可删除该项目的浏览器草稿和快照，服务端项目需另行管理。
- 右侧的「设计规格」支持表单和 JSON 导入。「任务规划」可手动编辑、导入任务或应用 Agent 生成的候选任务。切换「工作流」可查看或编辑依赖、自动布局、添加注释和导出 PNG。
- 「保存到浏览器」保留当前草稿。「保存快照」另存一份只读副本，每个项目保留最近 30 份。「本地历史」支持查看、逐条删除和清空当前项目的快照。

## 服务端规划

1. 在左栏展开「后端工作区」，创建或关联服务端项目，保存规格版本。
2. 选择「真实模型」或「测试样例」并发起规划。任务粒度、额外约束和策略可在「规划设置」调整。断线或刷新后可继续查询同一请求。
3. 审核候选并应用到草稿，点击「服务端编排」，在右侧查看依赖和并行批次。手动或导入的任务也可提交编排。
4. 展开「确认假设」，逐项确认低影响假设后保存计划版本。关键假设需要补充规格或修正任务。浏览器草稿可以在审核过程中独立保存。
5. 使用「版本与布局」查看历史版本、同步画布布局或导出完整计划包。出现版本冲突时，刷新服务端版本再核对当前草稿。

交换格式见 [Design Spec](../tech/artifacts/schema/design-spec.schema.json) 和 [TaskProposal](../tech/artifacts/schema/task-proposal.schema.json)。浏览器工作区使用 `flowstudio.workspace.v1`，会兼容旧版嵌套的注释坐标。

## 验证

```powershell
npm.cmd run build
npm.cmd test
npm.cmd run test:browser
```

浏览器测试使用生产构建及 Chrome、Chromium 或 Edge，可用 `CHROME_BIN` 指定浏览器。设置 `FLOWSTUDIO_TEST_BACKEND_URL` 可增加真实 HTTP 联调。测试会在该后端创建项目并执行 `diamond` 固定样例，请使用独立测试数据库。
