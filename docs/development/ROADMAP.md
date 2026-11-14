# 开发路线图
本轮止于设计；以下阶段须在设计审查后逐步实施，不代表已开始编码。

| 阶段 | 目标 | 出口门槛 |
|---|---|---|
| M0 约2～3天 | 评审、锁定契约与Windows兼容实验 | SQLite checkpoint、Send/reducer、interrupt恢复及DeepSeek JSON探针有实证；无Key仅完成其他实验 |
| M1 约1周 | 数据/契约/手动画布/Agent与模型配置 | 草稿可保存、冻结、校验；密钥不泄漏 |
| M2 约1～2周 | Planner、固定主图、真实工具、SSE | 智能计划可运行、并行输入真实传递、事件可补发 |
| M3 约1周 | 人工审批、恢复、Reviewer及受限修订 | 崩溃故障注入、审批幂等、真实交接和审查闭环 |
| M4 约1周 | Windows打包体验与验收 | TEST全套+REAL现场演示、证据包、已知限制清单 |
| P1 | 通用重规划/回放/优化 | 在P0稳定后逐项批准范围 |

估算按3～5人协作，非交付承诺。先验证最高风险，再完善UI，不用静态动画代替后端。

拟议启动（脚本尚未实现）：首次 `py -m venv .venv`，`.venv\Scripts\python -m pip install -r backend/requirements.lock`，`npm --prefix frontend ci`；日常 `powershell -File scripts/dev.ps1` 管理前后端并清理子进程；构建后 `powershell -File scripts/start.ps1` 启动单后端提供静态页。实现时验证执行策略无需全局放宽，端口冲突有明确报错。Python/Node版本在M0实测后锁定；不在设计里虚称安装通过。
