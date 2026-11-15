import specSchema from '../../tech/artifacts/schema/design-spec.schema.json';
import taskSchema from '../../tech/artifacts/schema/task-proposal.schema.json';
import derivationSchema from '../../tech/artifacts/schema/plan-derivation.schema.json';
import type { DesignSpecContent, TaskProposal } from './api/generated/contracts';
export type { Requirement, Task } from './api/generated/contracts';
import type { Task } from './api/generated/contracts';

export type Spec = DesignSpecContent;
// The editor keeps this shape even when it is an empty or incomplete draft.
export type Plan = TaskProposal;
const maxEdges = derivationSchema.properties.edges.maxItems;

export type Source = 'MANUAL' | 'IMPORTED' | 'PRESET';
export interface PlanningProvider {
  request(spec: Readonly<Spec>, signal: AbortSignal): Promise<Plan>;
}

export const emptySpec = (): Spec => ({
  schema_version: '1.0', product_name: '', background: '', goals: [], target_users: [],
  requirements: [], technical_constraints: [], development_constraints: [], delivery_requirements: [],
  acceptance_criteria: [], supplemental_text: '', confirmed_assumptions: [],
});
export const emptyPlan = (): Plan => ({ schema_version: '1.0', tasks: [], blocking_questions: [] });
export const newTask = (id: string): Task => ({
  task_id: id, name: '', description: '', category: '', stage: '', assigned_role: '', priority: 'medium',
  dependencies: [], inputs: [], deliverables: [], acceptance_criteria: [], source_requirement_ids: [],
  rationale: '', assumptions: [], estimated_effort: null,
});

export type Issue = { path: string; message: string };
type Schema = {
  $ref?: string; $defs?: Record<string, Schema>; anyOf?: Schema[];
  type?: string; const?: unknown; enum?: readonly unknown[]; oneOf?: Schema[];
  properties?: Record<string, Schema | undefined>; required?: string[]; additionalProperties?: boolean;
  items?: Schema; minItems?: number; maxItems?: number; uniqueItems?: boolean;
  minLength?: number; maxLength?: number; pattern?: string; exclusiveMinimum?: number;
};

// Implements the keywords emitted for DesignSpecContent and TaskProposal.
function check(schema: Schema, value: unknown, path = '', draft = false, root: Schema = schema): Issue[] {
  const error = (message: string) => [{ path: path || '/', message }];
  if (schema.$ref) {
    const name = schema.$ref.startsWith('#/$defs/') ? schema.$ref.slice(8) : '';
    const target = name && Object.hasOwn(root.$defs ?? {}, name) ? root.$defs?.[name] : undefined;
    return target ? check(target, value, path, draft, root) : error('无法解析契约中的类型引用');
  }
  const alternatives = schema.oneOf ?? schema.anyOf;
  if (alternatives) {
    const matches = alternatives.filter((branch) => !check(branch, value, path, draft, root).length).length;
    return (schema.oneOf ? matches === 1 : matches > 0) ? [] : error('不符合允许的数据结构');
  }
  if ('const' in schema && value !== schema.const) return error('值必须为 ' + String(schema.const));
  if (schema.enum && !schema.enum.includes(value)) return error('可选值为 ' + schema.enum.join('、'));
  switch (schema.type) {
    case 'string': {
      if (typeof value !== 'string') return error('必须是文本');
      const normalized = value.trim();
      if (!draft && [...normalized].length < (schema.minLength ?? 0)) return error('请填写此字段');
      if (!draft && /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(normalized)) return error('不能包含控制字符');
      if (!draft && [...normalized].length > (schema.maxLength ?? Infinity)) return error('文本超过长度限制');
      return !draft && schema.pattern && !new RegExp(schema.pattern).test(normalized) ? error('请使用字母开头的字母、数字、下划线或连字符') : [];
    }
    case 'number':
      return typeof value === 'number' && Number.isFinite(value) && (draft || value > (schema.exclusiveMinimum ?? -Infinity))
        ? [] : error('数值不符合范围');
    case 'null':
      return value === null ? [] : error('必须为 null');
    case 'array':
      if (!Array.isArray(value)) return error('必须是数组');
      if (!draft && value.length < (schema.minItems ?? 0)) return error('至少需要 ' + schema.minItems + ' 项');
      if (!draft && value.length > (schema.maxItems ?? Infinity)) return error('最多支持 ' + schema.maxItems + ' 项');
      if (!draft && schema.uniqueItems && new Set(value).size !== value.length) return error('不能包含重复项');
      return value.flatMap((item, index) => schema.items ? check(schema.items, item, path + '/' + index, draft, root) : []);
    case 'object': {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return error('必须是对象');
      const object = value as Record<string, unknown>;
      const fields = schema.properties ?? {};
      return [
        ...(schema.required ?? []).filter((key) => !Object.hasOwn(object, key))
          .map((key) => ({ path: path + '/' + key, message: '缺少必填字段' })),
        ...Object.entries(object).flatMap(([key, item]) => Object.hasOwn(fields, key)
          ? check(fields[key]!, item, path + '/' + key, draft, root)
          : schema.additionalProperties === false ? [{ path: path + '/' + key, message: '不支持此字段' }] : []),
      ];
    }
    default:
      return [];
  }
}

export function normalizeContractText<T extends Plan | Spec>(value: T): T {
  return JSON.parse(JSON.stringify(value, (_, field) => typeof field === 'string' ? field.trim() : field));
}

function duplicates(ids: string[], path: string): Issue[] {
  return [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))]
    .map((id) => ({ path, message: 'ID 重复：' + id }));
}

export function validateSpec(value: unknown): Issue[] {
  const issues = check(specSchema, value);
  return issues.length ? issues : duplicates((value as Spec).requirements.map(({ id }) => id.trim()), '/requirements');
}

export type Relation = { source: string; target: string };
export type Orchestration = { edges: Relation[]; batches: string[][]; order: string[]; stages: { id: string; tasks: string[] }[] };
export type Assessment = { issues: Issue[]; warnings: Issue[]; result?: Orchestration };

export function isWorkspaceDraft(spec: unknown, plan: unknown): boolean {
  return (spec === null || !check(specSchema, spec, '', true).length) && !check(taskSchema, plan, '', true).length;
}

export function validatePlanStructure(value: unknown): Issue[] {
  const issues = check(taskSchema, value);
  if (issues.length) return issues;
  (value as Plan).tasks.forEach((task, index) => {
    const path = '/tasks/' + index;
    issues.push(
      ...duplicates(task.dependencies.map((id) => id.trim()), path + '/dependencies'),
      ...duplicates(task.source_requirement_ids.map((id) => id.trim()), path + '/source_requirement_ids'),
      ...duplicates(task.deliverables.map(({ id }) => id.trim()), path + '/deliverables'),
      ...duplicates(task.assumptions.map(({ id }) => id.trim()), path + '/assumptions'),
    );
    if (task.estimated_effort && task.estimated_effort.max_hours < task.estimated_effort.min_hours) {
      issues.push({ path: path + '/estimated_effort', message: '最大工时不得小于最小工时' });
    }
  });
  return issues;
}

export function validateTaskProposal(value: unknown): Issue[] {
  const issues = validatePlanStructure(value);
  if (issues.length) return issues;
  const { tasks, blocking_questions } = value as TaskProposal;
  if (!tasks.length && !blocking_questions.length) {
    return [{ path: '/tasks', message: '任务为空时，提案必须包含至少一个待补充问题' }];
  }
  return duplicates(tasks.map(({ task_id }) => task_id.trim()), '/tasks');
}

export function assessPlan(value: unknown, spec: Spec): Assessment {
  const issues = validatePlanStructure(value);
  const warnings: Issue[] = [];
  if (issues.length) return { issues, warnings };
  const plan = normalizeContractText(value as Plan);
  const tasks = new Map(plan.tasks.map((task) => [task.task_id, task]));
  const requirements = new Set(spec.requirements.map(({ id }) => id.trim()));
  const covered = new Set<string>();
  const assumptionOwners = new Map<string, string>();
  issues.push(...duplicates(plan.tasks.map(({ task_id }) => task_id), '/tasks'));
  plan.blocking_questions.forEach((message, i) => issues.push({ path: '/blocking_questions/' + i, message }));
  const edges: Relation[] = [];
  const add = (path: string, message: string) => issues.push({ path, message });
  plan.tasks.forEach((task, i) => {
    const path = '/tasks/' + i;
    task.dependencies.forEach((source, j) => {
      if (source === task.task_id || !tasks.has(source)) add(path + '/dependencies/' + j,
        source === task.task_id ? '不能依赖自身' : '找不到上游任务 ' + source);
      else edges.push({ source, target: task.task_id });
    });
    task.source_requirement_ids.forEach((id, j) => {
      if (!requirements.has(id)) add(path + '/source_requirement_ids/' + j, '找不到需求 ' + id);
      else covered.add(id);
    });
    task.assumptions.forEach((assumption, j) => {
      const field = path + '/assumptions/' + j;
      const owner = assumptionOwners.get(assumption.id);
      if (owner !== undefined) {
        add(field, '假设 ID 重复：' + assumption.id + '，已用于任务 ' + owner);
      } else {
        assumptionOwners.set(assumption.id, task.task_id);
      }
      if (assumption.impact === 'critical') {
        add(field, '关键假设 ' + assumption.id + ' 需要补充信息：' + assumption.text);
      }
    });
    task.inputs.forEach((input, j) => {
      const field = path + '/inputs/' + j;
      if (input.kind === 'spec') {
        if (!requirements.has(input.requirement_id)) add(field, '找不到输入需求 ' + input.requirement_id);
      } else if (!task.dependencies.includes(input.task_id)) {
        add(field, '输入成果必须来自直接上游 ' + input.task_id);
      } else if (!tasks.get(input.task_id)?.deliverables.some(({ id }) => id === input.deliverable_id)) {
        add(field, '找不到上游交付 ' + input.deliverable_id);
      }
    });
  });
  if (plan.tasks.length) {
    spec.requirements.forEach(({ id, priority }, index) => {
      const requirementId = id.trim();
      if (covered.has(requirementId)) return;
      const issue = {
        path: '/requirements/' + index,
        message: (priority === 'must' ? '必需需求 ' : '需求 ') + requirementId + ' 未被任务覆盖',
      };
      (priority === 'must' ? issues : warnings).push(issue);
    });
  }
  if (edges.length > maxEdges) add('/tasks', '依赖连线最多支持 ' + maxEdges + ' 条，当前有 ' + edges.length + ' 条');
  if (issues.length || !tasks.size) return { issues, warnings };
  const indegree = new Map(plan.tasks.map((task) => [task.task_id, task.dependencies.length]));
  const children = new Map([...tasks.keys()].map((id) => [id, [] as string[]]));
  edges.forEach(({ source, target }) => children.get(source)!.push(target));
  const batches: string[][] = [];
  let ready = [...tasks.keys()].filter((id) => indegree.get(id) === 0);
  while (ready.length) {
    const batch = ready.sort();
    batches.push(batch);
    ready = [];
    for (const id of batch) {
      for (const child of children.get(id)!) {
        const count = indegree.get(child)! - 1;
        indegree.set(child, count);
        if (!count) ready.push(child);
      }
    }
  }
  const order = batches.flat();
  if (order.length !== tasks.size) {
    const visiting = new Set<string>(), visited = new Set<string>(), trail: string[] = [];
    function findCycle(id: string): string[] | undefined {
      if (visiting.has(id)) return [...trail.slice(trail.indexOf(id)), id];
      if (visited.has(id)) return;
      visiting.add(id);
      trail.push(id);
      for (const child of children.get(id)!) {
        const cycle = findCycle(child);
        if (cycle) return cycle;
      }
      trail.pop();
      visiting.delete(id);
      visited.add(id);
    }
    let cycle: string[] | undefined;
    for (const id of tasks.keys()) {
      cycle = findCycle(id);
      if (cycle) break;
    }
    return { issues: [{ path: '/tasks', message: '循环依赖：' + cycle?.join(' → ') }], warnings };
  }
  const stages = new Map<string, string[]>();
  for (const batch of batches) {
    for (const stage of [...new Set(batch.map((id) => tasks.get(id)!.stage))].sort()) {
      stages.set(stage, [...(stages.get(stage) ?? []), ...batch.filter((id) => tasks.get(id)!.stage === stage)]);
    }
  }
  return { issues, warnings, result: { edges, batches, order, stages: [...stages].map(([id, tasks]) => ({ id, tasks })) } };
}

export function linkError(plan: Plan, source: string, target: string): string | undefined {
  const tasks = new Map(plan.tasks.map((task) => [task.task_id, task]));
  const destination = tasks.get(target);
  if (!tasks.has(source) || !destination) return '找不到要连接的任务';
  if (source === target) return '不能依赖自身';
  if (destination.dependencies.includes(source)) return '该依赖已存在';
  if (plan.tasks.reduce((count, task) => count + task.dependencies.length, 0) >= maxEdges) return '依赖连线最多支持 ' + maxEdges + ' 条';
  const pending = [source], seen = new Set<string>();
  while (pending.length) {
    const id = pending.pop()!;
    if (id === target) return '此连接会形成循环依赖';
    if (seen.has(id)) continue;
    seen.add(id);
    pending.push(...(tasks.get(id)?.dependencies ?? []));
  }
}

export function removeTask(plan: Plan, id: string): Plan {
  return {
    ...plan,
    tasks: plan.tasks.filter((task) => task.task_id !== id).map((task) => ({
      ...task, dependencies: task.dependencies.filter((dependency) => dependency !== id),
      inputs: task.inputs.filter((input) => input.kind !== 'task' || input.task_id !== id),
    })),
  };
}

export function planState(plan: Plan, assessment: Assessment, current: boolean, edited: boolean) {
  if (!plan.tasks.length && !assessment.issues.length) return 'NO_PLAN';
  if (assessment.issues.length) return 'PLAN_INVALID';
  if (current) return 'PLAN_VALID';
  return edited ? 'REORCHESTRATION_REQUIRED' : 'PLAN_AVAILABLE';
}
