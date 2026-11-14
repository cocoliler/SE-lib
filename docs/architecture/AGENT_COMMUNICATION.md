# Agent 通信协议

编排器在每次派发、接收成果与审查反馈时存结构化消息。消息字段为 message_id、run_id、revision_id、task_id、attempt_id、sender、receiver、message_type、payload、timestamp、correlation_id 与 causation_id。

类型包括 TASK_DELEGATION（指向输入清单）、ARTIFACT_HANDOFF（生产者、接收者与 artifact_id/hash）、TASK_RESULT（结构化成果引用）、REVIEW_FEEDBACK（缺陷与证据）。工具作为 ToolOperation 独立存储，运行状态变化作为 Event 按 seq 推送。依赖边是运行条件，绑定是数据路径，消息是实际协作记录。界面不会把计划边显示为已发生交接。

接收 Agent 实际读取的字段记录在自身 Attempt.input_manifest。编排器核对同 run 内引用与 hash，限定读取范围，P0 只有经批准修订的同 run 旧产物可复用。只传必要内容和摘要；消息不含密钥、授权头或推理过程。correlation_id 关联完整调用，按 message_id 去重。详见[角色协作](MULTI_AGENT_ARCHITECTURE.md)。
