export const spec = {
  schema_version: '1.0', product_name: '验收项目', background: '本地验证',
  goals: ['校验工作流'], target_users: ['维护者'],
  requirements: [{ id: 'REQ_A', kind: 'functional', priority: 'must', text: '检查依赖', acceptance_criteria: ['报告回路'] }],
  technical_constraints: [], development_constraints: [], delivery_requirements: ['检查报告'],
  acceptance_criteria: ['可以导出'], supplemental_text: '', confirmed_assumptions: [],
};
export const task = (id, dependencies = []) => ({
  task_id: id, name: '任务 ' + id, description: '用于验证', category: 'dev', stage: 'build', priority: 'medium',
  assigned_role: 'developer', dependencies, inputs: [], deliverables: [{ id: 'OUT', text: '成果' }],
  acceptance_criteria: ['成果可读'], source_requirement_ids: ['REQ_A'], rationale: '', assumptions: [], estimated_effort: null,
});
export const plan = (...tasks) => ({ schema_version: '1.0', tasks, blocking_questions: [] });
