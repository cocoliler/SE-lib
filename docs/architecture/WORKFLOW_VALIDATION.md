# 编排验证与错误协议
Issue={code,severity:error/warning,path,message,task_ids:string[],edges:{source,target}[],suggestion}。
path 使用 JSON Pointer，例如 /tasks/2/dependencies/0。报告绑定 input_hash/rules_version，过期报告不能作为保存凭证。

| 错误码 | 示例 | 处置 |
|---|---|---|
| SPEC_REQUIRED | goals=[] | 规格页定位字段；阻止模型调用 |
| DUPLICATE_ID | 两个 task_id=A | 人工或模型重命名并更新引用 |
| MISSING_DEPENDENCY | B 依赖不存在的 X | 修正 ID 或补任务，不静默删边 |
| SELF_DEPENDENCY | A 依赖 A | 高亮自环并删除错误关系 |
| DUPLICATE_DEPENDENCY | B=[A,A] | 提示去重后重编排，不静默覆盖原输入 |
| CYCLE | A→B→A | 返回实际环，人工修复 |
| INVALID_STAGE / ROLE / CATEGORY | stage 不满足显式约束 | 改任务或规划约束，不编造新配置 |
| STAGE_EDGE_FORBIDDEN | 跨阶段依赖不满足显式约束 | 修依赖/阶段；不改变显示位置掩盖错误 |
| MISSING_INPUT | B 引用 A 不存在的 deliverable | 选择现有交付 ID 或更新生产者 |
| INPUT_NOT_DEPENDENCY | B 读取 A 成果但未依赖 A | 原子添加直接依赖并重校验 |
| UNKNOWN_REQUIREMENT | 引用旧版删除的需求 | 选择来源规格中的合法 ID |
| REQUIRED_UNCOVERED | must 需求没有任何任务引用 | 增补任务；是否实质覆盖需人工评审 |
| REQUIRED_CATEGORY | 指定必需类别却未出现 | 增补带验收任务 |
| UNCONFIRMED_ASSUMPTION | 保存未确认 low 假设 | 显示假设并请求确认 |
| CRITICAL_ASSUMPTION | 缺关键权限/范围仍推断 | 返回 NEEDS_INPUT，要求新规格 |
| POSSIBLE_DUPLICATE / ORPHAN | 标题相同或孤立任务 | warning；人工解释或修正 |
| REVISION_CONFLICT | expected_revision 过期 | 409；保留本地编辑，比较后重提 |

validation.valid 仅指 errors=[]；warnings 可存在。缺陷位置、字段名可定位，错误不只写“规划失败”。
结构/图/输入引用失败不可用户强制忽略。语义合理性以人工评审记录体现，不让模型评分覆盖硬错误。
规则用版本化纯函数注册表 {rule_id,version,severity,check}，规划参数仅配置已注册规则及参数，不执行导入字符串。
