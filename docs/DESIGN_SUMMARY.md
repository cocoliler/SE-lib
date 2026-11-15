# 通用设计摘要

FlowStudio 面向需求结构化、计划编排、开发执行、验证与反馈。课堂作业 2 聚焦从设计规格和 PM 生成的候选任务，到可校验、可修改、可冻结的开发计划。

## 当前能演示的流程

1. 创建空项目，填写结构化 Design Spec 或导入规格 JSON。演示时也可显式创建「会议室预约」项目。
2. 手动录入任务或导入 TaskProposal JSON。预览显示 JSON、诊断与可计算的任务和批次统计。
3. 重新编排。浏览器检查任务与成果引用、环、需求覆盖、假设和规模限制，然后按拓扑层计算并行批次。
4. 在列表和画布中使用同一组任务 ID。可搜索定位、编辑依赖、卡内编辑注释、自动布局、导出 PNG、保存草稿或记录只读本地快照。

## 正式规划链路的设计

- PM Agent 根据 SpecRevision 和可选 PlanningPolicy 生成 TaskProposal，以预算、有限重试和诊断约束模型调用。
- 服务端确定性编排器生成 PlanDerivation 和 ValidationReport，前端投影结果。坐标、视口和注释独立于业务顺序。
- 通过校验并完成假设确认后可保存不可变 PlanRevision，写入用 expected_revision 与幂等键处理冲突及重试。
- 任务规划、计划保存和实际执行分开。P2 再引入执行、成果验证与监督。

下一步把现有本地前端与 T02 项目/规格 API、T04 PM、T05 服务端编排器联调，再完成 T07 正式版本与 T08 REAL 验收。参见[实现审计](PROJECT_AUDIT.md)、[工作流编辑器](design/WORKFLOW_EDITOR.md)、[技术版系统架构](../tech/docs/system-architecture.md)和[开发路线](development/ROADMAP.md)。
