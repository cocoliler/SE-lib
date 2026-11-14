# FlowStudio 最小可运行原型

在仓库根目录运行，需要 Python 3.10 以上，无第三方依赖。

```powershell
python prototype/flowstudio.py
```

终端展示任务及依赖。输入 `y` 确认执行，其他输入取消。默认 TEST 使用固定测试角色，验证计划校验、人为审批、按依赖执行、上游成果传递、审查和持久化。可用 `--goal "你的需求"` 替换演示输入，自动化验证可用 `--approve`。

真实调用时，通过环境变量配置 `DEEPSEEK_API_KEY`，可选 `DEEPSEEK_MODEL`。REAL 模式将需求和中间成果发给 DeepSeek，规划和审查也会调用模型。运行命令如下。

```powershell
python prototype/flowstudio.py --mode real --goal "设计团队缺陷跟踪工具，并给出测试方案"
```

默认结果写入 `.flowstudio/prototype.db` 的 `runs` 和 `events` 表，可用 `--db` 选择非默认路径。每条事件含运行 ID、顺序和时间，任务结束事件持久化结构化成果。

此原型以 CLI 展示图的依赖关系并顺序执行。正式产品的 React Flow 界面、LangGraph、异步并行和恢复留在后续团队任务中。
