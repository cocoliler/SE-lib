# Windows 本地开发与运行
## 当前确实可运行的部分
现有仓库前端，要求Node满足frontend/package.json（当前≥22.12.0），不在本轮升级：
```powershell
Set-Location D:\Program01\TW1\frontend
npm ci
npm run dev
```
浏览器访问 Vite 输出地址。工作台可创建空项目，也可显式加载「会议室预约」PRESET。手动或导入任务可在浏览器完成预检、编排与快照保存；工作区显示 PM Agent 尚未连接。

生产构建与前端验证分别执行 `npm run build`、`npm test`、`npm run test:browser`。浏览器测试读取生产构建，可用 `CHROME_BIN` 指定 Chromium。契约生成和一致性检查见[工程组织](PROJECT_STRUCTURE.md)。
独立CLI分支不是main网页服务；本地prototype缓存不构成运行入口。

## 后端（已可运行，从 backend 目录启动）
```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD;$(Split-Path -Parent $PWD)\tech"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
也可直接执行 `.\scripts\dev.ps1`（热重载，首次自动建 venv）或 `.\scripts\start.ps1`（无热重载）。两个脚本都会把 `backend` 与 `tech` 加入 PYTHONPATH；契约包不在 backend 内，缺这条会导入失败。
`PYTHONPATH` 必须同时包含 `backend`（应用与 T05 编排器）和 `tech`（flowstudio_contracts）。API 文档在 `http://127.0.0.1:8000/docs`；契约里没有 `/health`，就绪用 `GET /api/v1/projects` 判断。
Vite /api代理到8000；生产由FastAPI提供静态dist（`FLOWSTUDIO_FRONTEND_DIST`），保持同源。不需要Docker/Redis/云数据库。
数据目录默认 `backend/.flowstudio`（可用 `FLOWSTUDIO_DATA_DIR` 覆盖），数据库文件 `flowstudio.db`；启动持有实例锁并按 `FLOWSTUDIO_USE_ALEMBIC` 执行迁移/建表。更新前备份，恢复后integrity_check。
API Key经后端环境变量DEEPSEEK_API_KEY读取；.env不入Git、不下发前端；模型实际ID配置单独保存，不能随文档假定某个ID永久可用。
无Key时仍可编辑/读历史和显式TEST；REAL 由默认引擎直接返回 `MODEL_AUTH`（不静默降级），待 C 的 T04 适配器接入。
测试命令：仓库根 `python -m pytest`（pytest.ini 已配置 testpaths 与 PYTHONPATH）；编排器 `cd backend; python -m unittest discover -s tests`。契约漂移：`python backend/tools/export_openapi.py`。
