# 多 Agent 体系
| 角色 | 输入 | 输出/验收 | 能力边界 |
|---|---|---|---|
| Planner | goal/spec/constraints/可用角色 | PlanRevision；Schema+DAG+预算合法 | 不执行任务 |
| Coordinator | ready任务/角色能力/摘要 | assignment或handoff/replan建议 | 编排器验证后生效 |
| Research | 需求/允许来源 | sources[{url,title,evidence}],options | 未配置联网只能输入资料分析 |
| Executor | TaskSpec+输入artifact | output_schema对应结果 | 工具白名单、迭代和超时 |
| Reviewer | 标准/成果/机器验证报告 | verdict:pass/revise/fail，findings[{criterion_id,severity,evidence_ref,suggestion}] | 不能推翻机器失败 |
| Architecture | 技术选项/criteria | modules/interfaces/decisions | 自定义Executor角色 |
| Planning/TestDesign | 架构/criteria | tasks或cases/coverage | 自定义Executor角色 |

AgentVersion字段：agent_id/version/name/role/description/system_prompt/model_profile_version/parameters/tool_permissions/input_schema/output_schema/max_steps/context_policy/created_at。保存产生不可变版本，run固定引用；编辑不影响历史，停用阻止新引用。注册校验工具存在、模型能力支持、schema合法、max_steps不超run限制；复用通过模板复制并生成新身份。

每个Agent循环：构造有限上下文→模型决策→若tool_call则校验权限/参数/预算→调用并记录→返回观察→下一轮；遇到结构化final则校验输出。达到步数或时间失败，不能用无界递归。内部推理过程不作为监控承诺，只展示输入摘要、模型可见输出、工具与决策证据。

上下文由系统规则、当前任务、验收标准、依赖artifact引用和必要摘要组成；不拼接全部历史。默认输入预算为模型context上限扣除输出预留后的70%，超限优先按字段裁剪可选上下文，必要数据不能静默截断；摘要附原文hash与引用。检索/提示注入不能变更system权限。Reviewer与生产者使用不同角色上下文；同一模型可用但不等于独立质量保证。
