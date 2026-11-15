import { useState } from 'react';
import { Issues } from './forms';
import type { Issue, Orchestration, Plan, Spec, Task } from './plan';

export type ImportCandidate = { filename: string; issues: Issue[] } & (
  { kind: 'spec'; value: Spec } | { kind: 'plan'; value: Plan; warnings: Issue[]; result?: Orchestration }
);

export function ImportPreview({ candidate, apply, cancel }: {
  candidate: ImportCandidate; apply(): void; cancel(): void;
}) {
  const tasks = candidate.kind === 'plan' ? candidate.value.tasks : [];
  const warnings = candidate.kind === 'plan' ? candidate.warnings : [];
  const result = candidate.kind === 'plan' ? candidate.result : undefined;
  return <section className="import-workspace" aria-labelledby="import-heading">
    <header className="workspace-heading">
      <div><h1 id="import-heading">导入预览</h1><p className="muted">{candidate.filename}</p></div>
      <div className="actions">
        <button onClick={cancel}>取消导入</button>
        <button className="primary" onClick={apply}>应用导入</button>
      </div>
    </header>
    <div className="import-grid">
      <section className="panel json-preview" aria-label="JSON 内容">
        <h2>{candidate.kind === 'plan' ? '任务计划 JSON' : '设计规格 JSON'}</h2>
        <pre tabIndex={0}><code>{JSON.stringify(candidate.value, null, 2)}</code></pre>
      </section>
      <section className="panel import-review" aria-label="导入校验">
        <div className="panel-title"><h2>校验结果</h2>
          <span className={'badge ' + (candidate.issues.length ? 'plan_invalid' : 'plan_valid')}>
            {candidate.issues.length ? candidate.issues.length + ' 项待修正' : warnings.length ? '校验通过 · 有警告' : '校验通过'}
          </span></div>
        {candidate.kind === 'spec' ? <div className="import-spec">
          <strong>{candidate.value.product_name}</strong>
          <span className="muted">{candidate.value.requirements.length} 项需求</span>
        </div> : <>
          <dl className="import-stats">
            <div><dt>任务</dt><dd>{tasks.length}</dd></div>
            <div><dt>有效依赖</dt><dd>{result?.edges.length ?? '—'}</dd></div>
            <div><dt>并行批次</dt><dd>{result?.batches.length ?? '—'}</dd></div>
            <div><dt>最大并行度</dt><dd>{result ? Math.max(...result.batches.map((batch) => batch.length)) : '—'}</dd></div>
          </dl>
          {result && <BatchPanel result={result} tasks={tasks} />}
        </>}
        <Issues issues={candidate.issues} />
        <Issues issues={warnings} warning />
        <p className="muted">{candidate.kind === 'spec' ? '应用后会替换当前规格。' : '应用后会替换当前任务和节点位置，保留注释。'}</p>
      </section>
    </div>
  </section>;
}

export function BatchPanel({ result, tasks, select }: {
  result: Orchestration; tasks: Task[]; select?(id: string): void;
}) {
  const taskNames = new Map(tasks.map(({ task_id, name }) => [task_id, name || task_id]));
  return <details className="orchestration" aria-label="编排结果">
    <summary>并行批次 <span>{result.batches.length} 批 · {result.edges.length} 条依赖</span></summary>
    <ol className="batch-cards">
      {result.batches.map((batch, index) => <li key={index} data-tone={index % 4}>
        <span className="batch-title">批次 {index + 1}<small>{batch.length} 项任务</small></span>
        <ul>{batch.map((id) => <li key={id}>{select
          ? <button className="batch-task" onClick={() => select(id)}>{taskNames.get(id) ?? id}</button>
          : <span>{taskNames.get(id) ?? id}</span>}</li>)}</ul>
      </li>)}
    </ol>
  </details>;
}

export function TaskNavigator({ tasks, result, selected, locate }: {
  tasks: Task[]; result?: Orchestration; selected: string | null; locate(id: string): void;
}) {
  const [query, setQuery] = useState('');
  const term = query.trim().toLocaleLowerCase();
  const visible = tasks.filter(({ task_id, name, assigned_role }) => [task_id, name, assigned_role]
    .some((value) => value.toLocaleLowerCase().includes(term)));
  const groups = new Map<string, Task[]>();
  if (result) {
    const lookup = new Map(visible.map((task) => [task.task_id, task]));
    result.batches.forEach((batch, index) => {
      const matches = batch.flatMap((id) => lookup.has(id) ? [lookup.get(id)!] : []);
      if (matches.length) groups.set('批次 ' + (index + 1), matches);
    });
  } else {
    for (const task of visible) {
      const label = task.stage || '未设置阶段';
      groups.set(label, [...(groups.get(label) ?? []), task]);
    }
  }
  return <aside className="panel task-navigator" aria-label="画布任务索引">
    <div className="panel-title"><h2>任务索引</h2><span className="muted">{tasks.length}</span></div>
    <input type="search" aria-label="搜索画布任务" placeholder="搜索名称或 ID" value={query}
      onChange={(event) => setQuery(event.target.value)} />
    {!visible.length && <p className="muted">没有匹配的任务</p>}
    {[...groups].map(([label, group]) => <details key={label} open>
      <summary>{label} <small>{group.length} 项</small></summary>
      <ul>{group.map((task) => <li key={task.task_id}>
        <button onClick={() => locate(task.task_id)} aria-pressed={task.task_id === selected}>
          <span>{task.name || '未命名任务'}</span><code title={task.task_id}>{task.task_id}</code>
        </button>
      </li>)}</ul>
    </details>)}
  </aside>;
}
