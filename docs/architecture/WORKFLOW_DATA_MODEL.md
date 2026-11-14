# 工作流与接口契约

下表是待实施的数据契约。Pydantic 为唯一来源，导出 OpenAPI、JSON Schema 与 TypeScript。写入拒绝未知字段，明确 schema_version。JSON 总体及字符串限制在 Phase 2 锁定，业务 JSON 不包含运行时函数或 React Flow 对象。

| 对象 | 必需属性与关系 |
|---|---|
| SpecRevision | id、spec_id、revision、name、description、goal、inputs[]、deliverables[]、constraints[]、completion_conditions[]、acceptance_criteria[{id,text}]、priority、created_at |
| PlanRevision | id、plan_id、revision、spec_revision_id、tasks[]、hash、created_at。规范化业务 JSON 的 SHA-256，排除 layout |
| TaskSpec | task_id、task_name、description、dependencies[]、assigned_agent、input[]、expected_output{schema_id,artifact_key}、acceptance_criteria[]；人工任务 kind=approval，其余 kind=agent |
| InputBinding | name、source_kind=spec/artifact、source_task_id（artifact 必需）、artifact_key（artifact 必需）、json_pointer、schema_id。源任务必须为直接依赖 |
| Run | id、plan_revision_id、active_revision_id、mode、status、generation、graph_version、budget、last_seq、parent_run_id（可选） |
| TaskRun / Attempt | run_id、revision_id、task_id、status、agent_version、attempt_id；Attempt 附 input_manifest、started_at、ended_at、error |
| Artifact | id、attempt_id、artifact_key、sha256、schema_id、content。input_manifest 逐项记录来源 id、hash 与实际读取的字段 |
| Review / Finding | verdict=pass/revise/fail、findings[{id,criterion_id,task_id,evidence_ref,reason,suggestion}]、machine_checks[]。失败须有具体 findings |
| Approval | id、run_id（首次计划批准可为空至创建 run）、kind、target_hash、status、deadline、decision |
| Layout | plan_revision_id 或草稿键、positions、notes、viewport，仅用于编辑视图 |

候选 Plan 不含执行状态。API 读图时以稳定 task_id 合并 TaskRun.status，未执行节点显示 PENDING。迁移适配将 task_id/task_name/dependencies 映射到当前前端 id/title/depends_on。旧草稿导入须填写新增字段并走后端校验，确认动作在适配层外。

| API | 语义 |
|---|---|
| POST /api/specs，PUT /api/specs/{id} | 创建或以 expected_revision 更新规格，返回不可变修订 |
| POST /api/plans，GET /api/plans/{id} | 用 spec_revision_id 与 mode 请求规划。POST 返回 202 和计划 ID，GET 返回 PLANNING/READY/FAILED 及候选或错误 |
| PUT /api/plans/{id} | 以 expected_revision 提交修改并校验 |
| POST /api/runs | 确认 plan_id/revision/hash 与 idempotency_key，原子创建批准记录和运行 |
| GET /api/runs/{id} 和 /events | 一致快照（含 snapshot_seq），及 SSE 补发 |
| POST /api/runs/{id}/cancel 和 /approvals/{id}/decision | 幂等取消，或对 run 内审批提交 decision 与 target_hash |

校验返回 422，修订或决定冲突返回 409，游标失效走 SSE reset，预算耗尽有独立错误码。相同幂等键和请求摘要返回原结果，同键异内容拒绝。
