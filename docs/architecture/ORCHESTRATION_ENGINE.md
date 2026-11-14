# 多 Agent 编排器详细设计

| 方案 | 复杂度与恢复 | 调试与画布映射 |
|---|---|---|
| A 固定 LangGraph 主图 + 动态计划数据 | 一次编译，run 固定主图版本；业务层统一校验、审批和恢复边界 | 主图阶段稳定，用 task_id 把动态任务映射到用户画布 |
| B 每次由计划生成执行图 | 每个版本需重新编译，恢复时须能重建完全一致的图；修订时管理更多拓扑版本 | 图较直观，然而编译节点与工具/审批节点仍需关联 |

首版选 A。主图 load → dispatch → workers → collect → verify → review，按程序条件走 finish 或 repair_gate。用户画布是计划投影。第一轮串行联调和最终图复用同一任务契约。在 [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) 中 Send 支持动态参数并行，将具体任务作为 worker 输入，按 attempt_id 归并通过校验的结果引用。

## 执行算法

1. 校验批准的快照，将任务写为 PENDING。编排器按拓扑和 task_id 稳定选取就绪任务：依赖全部 COMPLETED，required 输入在业务库可读并通过 Schema。
2. 一条活动运行，每轮最多 2 项。事务领取任务并递增调用预算，建立 Attempt、generation 和输入引用清单；以 Send 调用 Agent，同轮汇聚后重新计算 READY。慢分支可延迟下一轮，首版接受。
3. 同一 task_id 在一次 revision 只有一个活跃 attempt。成功先原子落成果、状态和事件，再返回引用给图；同键同 hash 幂等，异 hash 拒绝。失败标注分类和尝试次数，依赖任务 BLOCKED，允许独立分支收敛。若必需任务失败，本轮最终 FAILED，可查看部分成果。无就绪、无等待且仍有未完成任务为 DEADLOCK，终止。
4. 全部必需任务完成后生成机器验证清单，Reviewer 审查冻结规格与引用。确定性失败不能被覆盖。pass 且检查通过才 COMPLETED。
5. revise 时 Reviewer 指明 task_id、criterion_id 和证据。编排器仅支持一次定向修订，重做缺陷生产者和受影响下游，其他成果按 hash 复用。校验新 revision，人工批准后追加版本及新 Attempt，旧记录可查。拒绝、超时、不可修复或再次不合格即 FAILED。

初始确认在启动前完成。运行内审批先以稳定键幂等写入业务审批对象，安全边界才调用 interrupt。P0 主图使用内存 checkpointer，thread_id 固定为 run_id。同进程批准后由唯一运行驱动器读取已提交决定，调用 Command(resume=decision)，恢复节点核对审批 ID 和目标 hash。可选 SQLite checkpointer 跨重启恢复在 P1 实验。[Interrupt 文档](https://docs.langchain.com/oss/python/langgraph/interrupts)说明恢复重进节点，故等待节点内不发模型请求或执行工具。

首版上限：2–12 个任务、并发 2、30 次模型调用/100000 token 预算、请求超时 60 秒、活动运行截止 20 分钟、人工审批 24 小时。一轮临时错误最多再试一次，规划格式最多修复两次，修订最多一次。请求前原子预留额度；未知 usage 保留预留并标记未知。预算不因修订清零。工具不允许外部副作用，权限不足终止。
