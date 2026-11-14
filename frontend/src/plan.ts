export type Task = { id: string; title: string; depends_on: string[] };
export type Plan = { tasks: Task[] };

export const examplePlan: Plan = {
  tasks: [
    { id: 'spec', title: '整理需求', depends_on: [] },
    { id: 'design', title: '起草方案与测试', depends_on: ['spec'] },
  ],
};

export function linkError(plan: Plan, source: string, target: string): string | null {
  const tasks = new Map(plan.tasks.map((task) => [task.id, task]));
  const destination = tasks.get(target);
  if (!tasks.has(source) || !destination) return '找不到要连接的任务。';
  if (source === target) return '任务不能连接到自身。';
  if (destination.depends_on.includes(source)) return '这两项任务之间已存在该依赖。';

  const pending = [source];
  const seen = new Set<string>();
  while (pending.length) {
    const id = pending.pop()!;
    if (id === target) return '这条连线会形成循环依赖，请检查上下游方向。';
    if (seen.has(id)) continue;
    seen.add(id);
    pending.push(...(tasks.get(id)?.depends_on ?? []));
  }
  return null;
}
