export type Task = { id: string; title: string; depends_on: string[] };
export type Plan = { tasks: Task[] };

export const examplePlan: Plan = {
  tasks: [
    { id: 'spec', title: '整理需求', depends_on: [] },
    { id: 'design', title: '起草方案与测试', depends_on: ['spec'] },
  ],
};

export function canLink(plan: Plan, source: string, target: string): boolean {
  const tasks = new Map(plan.tasks.map((task) => [task.id, task]));
  const destination = tasks.get(target);
  if (!tasks.has(source) || !destination || destination.depends_on.includes(source)) return false;

  const pending = [source];
  const seen = new Set<string>();
  while (pending.length) {
    const id = pending.pop()!;
    if (id === target) return false;
    if (seen.has(id)) continue;
    seen.add(id);
    pending.push(...(tasks.get(id)?.depends_on ?? []));
  }
  return true;
}
