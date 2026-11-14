# Windows 本地运行

目前 main 可运行前端。Node 22.12 或兼容版本，PowerShell 在仓库根目录执行 `npm --prefix frontend ci` 与 `npm --prefix frontend run dev`；地址由 Vite 输出。独立原型分支可用 `python prototype/flowstudio.py` 执行 TEST。正式网页后端命令以下为计划。

1. Phase 2 在 Windows 验证并锁定 Python、Node、依赖和 SQLite 版本。通过 `py -m venv .venv` 建环境，使用虚拟环境解释器从锁文件安装。
2. 开发用 `powershell -File scripts/dev.ps1` 启动 loopback FastAPI 与 Vite。Vite 代理 /api。脚本报告端口冲突和健康状态，退出回收所属进程。
3. 构建用 `npm --prefix frontend run build`。交付脚本 `scripts/start.ps1` 启动单进程，后端提供静态构建和 API。
4. REAL 用后端环境变量 `DEEPSEEK_API_KEY`，可选 `DEEPSEEK_MODEL`。凭据不响应给浏览器、不入 Git，日志去除授权头和敏感字段。无 Key 可启动 TEST 或阅读记录。联网仅在启用真实模型时发生。
5. 数据目录 `.flowstudio/` Git 忽略，SQLite 本机磁盘。运行启动检查版本和锁，迁移前备份，停止进程后恢复备份并完整性检查。并发、超时和调用额度见[编排引擎](../architecture/ORCHESTRATION_ENGINE.md)。

Windows 验收用全新 checkout，运行两条模式、重启查询历史、验证 Key 未进产物和错误日志。禁止 Docker、Redis、Kafka、消息总线、云数据库及集群。
