# 功能验收
所有项目当前状态：NOT_RUN。本文件是测试规范，不是通过报告。REAL门槛需配置DeepSeek Key并允许实际费用，在实施阶段执行；TEST通过不能替代REAL。

| ID | Given/When | 必须观察到的结果/证据 |
|---|---|---|
| A01 规划 | 输入演示规格并调用真实Planner | 非硬编码JSON、合法图、模型call记录与usage |
| A02 非法图 | 注入重复ID/环/缺角色/越权工具 | 422字段定位；修复最多2次后终止 |
| A03 编辑审批 | AI计划人工改后批准，另标签页旧版本提交 | 只运行批准hash；旧revision 409 |
| A04 并行 | 两个独立研究任务延迟不同 | 时间区间重叠，最大并发不超2，汇聚输入hash正确 |
| A05 交接 | Research提出Architecture handoff | request/accepted/ack；active_agent改变；后续模型实际消费同artifact |
| A06 机器验证 | 缺少必需interface或criterion覆盖 | 验证失败不能被Reviewer pass覆盖 |
| A07 审查 | 注入漏测状态流转的成果 | Reviewer结构化revise；批准后新增任务版本与重审，保留旧成果 |
| A08 终止 | Reviewer持续不通过/工具反复失败 | 修订、步数、调用、token任一上限触发，不能无限循环 |
| A09 暂停取消 | 在途模型请求时pause/cancel | pause阻止新claim，在途继续；cancel晚到结果不改终态 |
| A10 断线 | 断SSE后状态继续变化再重连 | 无漏事件，重复去重，过期游标重取快照 |
| A11 恢复 | 在业务提交后checkpoint前杀进程 | 已落库结果复用；不重复副作用；未知模型请求人工确认 |
| A12 审批恢复 | interrupt后重启并重复批准 | 同thread继续且仅一次消费决定；过期/hash不符拒绝 |
| A13 工具 | 越界文件、链接、私网跳转、未批准写操作 | 权限网关阻止并记录脱敏错误 |
| A14 模型失败 | 429/超时/坏JSON/不支持参数 | 有限重试；未知usage不计零；错误可定位 |
| A15 测试模式 | 无Key运行TEST | 固定种子可复现、全程TEST标识、不得显示REAL通过 |
| A16 UI | 100节点编辑分组布局撤销与历史查看 | 视图不改变业务图，达性能目标或报告差距 |
| A17 Windows | 全新支持环境按脚本启动 | 无Docker等服务，端口冲突/退出/备份恢复清楚 |
| A18 持久性 | 磁盘满/业务事务失败/不兼容图版本 | 停止派发，不显示未提交成功，不猜测续跑 |

## REAL证据协议
固定输入fixture及hash；保存脱敏模型profile/模型名/依赖锁/Agent与计划版本；记录每个模型请求时间、provider_request_id（若提供）、usage或unknown、输入artifact hash、输出hash；执行Planner/Research/Architecture/Planning/TestDesign/Reviewer真实调用。断言前后产物被实际消费，改变输入需求应引起相关下游输出变化。保留一次正常通过、一次人工植入缺陷的修订分支；植入需明确标记为测试干预，不能伪称模型自然犯错。

导出manifest、plan.json、events.jsonl、artifacts、review.json、测试结果与运行截图；禁止导出Key或敏感原始提示。真实输出不做全文快照断言，使用schema、引用完整性、criteria覆盖及人工质量评审。第三方调用可核对请求记录，UI动画不是证据。
