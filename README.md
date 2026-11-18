# FlowStudio

FlowStudio 把设计规格转成可审核的任务计划。可以手动拆解任务，也可以让 PM Agent 生成候选，再用工作流画布查看依赖、执行顺序和并行批次。

## 快速开始

需要 Windows PowerShell、Python 3.11+ 和 Node.js 22.12+（含 npm）。以下命令从仓库根目录运行。

### 1. 启动后端

```powershell
Set-Location backend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

首次启动会创建虚拟环境并安装依赖。保持窗口运行，在 [API 文档](http://127.0.0.1:8000/docs) 确认后端已启动。

### 2. 启动前端

另开一个 PowerShell 窗口，从仓库根目录运行：

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

打开 [FlowStudio](http://127.0.0.1:5173/)。如果找不到 `npm.cmd`，确认已安装带 npm 的 Node.js，再打开新的 PowerShell 窗口。

### 3. 用内置项目体验编排

1. 点击 **「从示例创建」**，打开自带规格和任务的「会议室预约」示例。
2. 展开左栏 **「后端工作区」**，点 **「创建同名服务端项目」**，再点 **「保存规格版本」**。
3. 在右侧进入 **「任务规划」**，点左栏 **「服务端编排」**。切换 **「工作流」** 查看依赖箭头和画布下方的并行批次。
4. 如有待确认假设，展开 **「确认假设」** 逐项检查，再点 **「保存计划版本」**。可以在 **「版本与布局」** 中查看版本或导出完整计划包。

内置项目无需 API 密钥。如果只想查看本地编排，可直接在「任务规划」点击「重新编排」。

### 4. 可选：让 Agent 生成任务

把 [`backend/.env.example`](backend/.env.example) 复制为 `backend/.env`，填写以下配置，再重启后端：

```dotenv
DEEPSEEK_API_KEY=填写你的实际密钥
FLOWSTUDIO_DEFAULT_MODEL=deepseek-flash
FLOWSTUDIO_MODEL_ALLOWLIST=deepseek-flash
```

新建项目，填写或导入设计规格并保存规格版本。在「后端工作区」选择 **「真实模型」→「发起规划」**。规划成功后，审核并应用候选任务，再进行编排。若只想测试提交和轮询，可用 **「测试样例」→ `diamond`**，此样例要求规格包含需求 ID `R1` 和 `R2`。

更多说明见 [前端使用指南](frontend/README.md) 和 [Windows 本地部署](docs/development/LOCAL_DEPLOYMENT.md)。

## 交付材料

P0 交付范围、复现命令、证据和剩余风险见 [交付报告](delivery/DELIVERY_REPORT.md)；
机器可读版本与输入清单见 [MANIFEST](delivery/MANIFEST.json)。
