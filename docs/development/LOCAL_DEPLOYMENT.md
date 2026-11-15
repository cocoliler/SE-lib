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

## 后端目标方案（尚未实施，不是现成命令）
选定兼容Python版本后建立backend虚拟环境和锁文件，安装FastAPI/Pydantic/SQLAlchemy/Alembic/模型客户端；
应用入口约定backend/app/main.py，开发命令计划为python -m uvicorn app.main:app --host 127.0.0.1 --port 8000（从backend目录启动）。
Vite /api代理到8000；生产由FastAPI提供静态dist，保持同源。不需要Docker/Redis/云数据库。
数据目录.flowstudio，默认文件flowstudio.db；启动持有实例锁并执行迁移版本检查。更新前备份，恢复后integrity_check。
API Key经后端环境变量DEEPSEEK_API_KEY读取；.env不入Git、不下发前端；模型实际ID配置单独保存，不能随文档假定某个ID永久可用。
无Key时仍可编辑/读历史和显式TEST，REAL显示配置错误。Windows后端安装、路径/编码、代理及离线行为由Phase1/6验收。
