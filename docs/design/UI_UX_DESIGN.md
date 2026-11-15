# UI/UX、信息架构与用户旅程
## 页面组织
工作台 /projects：最近项目、规格更新时间、最近计划版本和创建入口。
项目工作区 /projects/:id：顶部项目名与版本，主导航“规格 / 计划”；计划内部“任务列表 / 工作流”切换。
校验报告作为底部/侧边抽屉；历史版本为选择器+详情抽屉。避免为任务、验证、历史建立三套重复页面。
P2 增加“执行 / 成果验证”，没有实现前不显示可用入口。

## 桌面结构
顶部栏56px；窄侧栏56px；画布工具栏40px；详情面板360px（可调320–480）；画布占剩余空间。
≥1440px 同时显示画布与右侧详情；1024–1439px详情覆盖画布；<1024px推荐任务列表并保留滚动，不宣称移动端画布完整支持。
规格页宽度最大960px，分“产品概况 / 需求条目 / 约束与验收”；需求行含稳定ID、类型、优先级和验收编辑。
非首次进入画布时规格入口为“规格 vN”按钮+一行摘要；不占大段 textarea。点击抽屉编辑，保存新规格后回到计划并标旧来源。

## 组件树
```text
AppShell
 ├ ProjectSwitcher / ProjectList
 └ ProjectWorkspace
    ├ WorkspaceHeader (version, mode badge, primary action)
    ├ SpecEditor (RequirementRows, Constraints, ImportPreview)
    └ PlanWorkspace
       ├ PlanningControls (granularity, model, optional policy)
       ├ TaskTable | WorkflowCanvas
       │              ├ CanvasToolbar / TaskNode / StageGroup / NoteNode
       │              └ MiniMap / ViewportControls
       ├ TaskInspector (details, inputs, deliverables, requirements)
       ├ ValidationDrawer (IssueList → focus task/edge)
       └ HistoryDrawer
```

## 用户旅程与状态
1. 新项目空状态只给“填写规格”“导入JSON”，示例放次级入口，并标“示例输入”。
2. 保存规格失败保留输入，字段错误就近显示，汇总可跳转；导入显示预览而非直接替换。
3. 生成时按钮禁用重复请求，显示“正在规划”及耗时，无虚构百分比；允许查看旧版；轮询失败显示连接问题，不把后台状态擅自判失败。
4. 关键缺信息进入“需补充规格”；非关键假设在候选顶部显示，逐条确认后保存。REAL/TEST持续可见。
5. 返回候选先看任务覆盖和问题，任务列表与画布使用同一store；点节点打开详情，不自动铺满配置。
6. 编辑产生dirty并提示“待重新编排”；校验完成且hash一致才显示新批次；无效结果保留编辑与诊断。
7. 保存冲突保留本地候选并展示最新版本；用户选择重新应用修改，不能静默覆盖。
8. 历史默认只读；“复制为新候选”后进入编辑。断网仍可查看历史，生成需要模型服务。

错误toast用于瞬时反馈，阻断问题长期保留于表单/校验抽屉。所有失败都有明确重试或返回路径。
