import { cloneElement, useId, useState, type ReactElement } from 'react';
import { validatePlanStructure, type Issue, type Requirement, type Spec, type Task } from './plan';

export function Field({ label, children, error }: {
  label: string; children: ReactElement<{ 'aria-invalid'?: boolean; 'aria-describedby'?: string }>; error?: string;
}) {
  const errorId = useId();
  return <label className="field"><span>{label}</span>
    {error ? cloneElement(children, { 'aria-invalid': true, 'aria-describedby': errorId }) : children}
    {error && <small className="spec-error" id={errorId} aria-hidden="true">{error}</small>}
  </label>;
}

export function Lines({ label, value, onChange, disabled, error }: {
  label: string; value: string[]; onChange(value: string[]): void; disabled?: boolean; error?: string;
}) {
  return <Field label={label} error={error}><textarea rows={2} value={value.join('\n')} disabled={disabled}
    placeholder="每行一项" onChange={(event) => onChange(event.target.value.split('\n'))}
    onBlur={() => { if (value.some((line) => !line.trim())) onChange(value.filter((line) => line.trim())); }} /></Field>;
}

export function Issues({ issues, focus, warning = false }: { issues: Issue[]; focus?(index: number): void; warning?: boolean }) {
  if (!issues.length) return null;
  const label = warning ? '校验警告' : '校验问题';
  return <section className={warning ? 'issues warnings' : 'issues'} aria-label={label}>
    <h3>{issues.length} 项{label}</h3>
    <ul>{issues.map(({ path, message }, index) => {
      const task = /^\/tasks\/(\d+)(?:\/|$)/.exec(path);
      return <li key={index}>
        {task && focus ? <button className="link" onClick={() => focus(Number(task[1]))}>{path}</button> : <code>{path}</code>}
        <span>{message}</span>
      </li>;
    })}</ul>
  </section>;
}

const overviewLists = [['goals', '目标'], ['target_users', '目标用户']] as const;
const acceptanceLists = [['delivery_requirements', '交付要求'], ['acceptance_criteria', '总体验收标准']] as const;
const optionalLists = [
  ['technical_constraints', '技术约束'], ['development_constraints', '开发约束'],
  ['confirmed_assumptions', '已确认假设'],
] as const;
type SpecList = typeof overviewLists[number] | typeof acceptanceLists[number] | typeof optionalLists[number];

export function SpecEditor({ spec, issues, setSpec }: { spec: Spec; issues: Issue[]; setSpec(spec: Spec): void }) {
  const [showMissing, setShowMissing] = useState(false);
  const showAll = showMissing || issues.length <= 2;
  function error(path: string, label: string) {
    const problem = issues.find((issue) => issue.path === path || issue.path.startsWith(path + '/'));
    if (!problem) return;
    if (problem.message === '请填写此字段' || problem.message.startsWith('至少需要')) {
      if (showAll) return '请填写' + label;
      return;
    }
    return problem.message;
  }

  function update(index: number, patch: Partial<Requirement>) {
    setSpec({ ...spec, requirements: spec.requirements.map((item, i) => i === index ? { ...item, ...patch } : item) });
  }

  function list([key, label]: SpecList) {
    return <Lines key={key} label={label} error={error('/' + key, label)} value={spec[key]}
      onChange={(value) => setSpec({ ...spec, [key]: value })} />;
  }

  function addRequirement() {
    setSpec({ ...spec, requirements: [...spec.requirements, {
      id: 'REQ_' + crypto.randomUUID().slice(0, 8), kind: 'functional', text: '', priority: 'must', acceptance_criteria: [],
    }] });
  }

  const requirementIssue = issues.find((issue) => issue.path === '/requirements');
  const hasOptional = !!spec.supplemental_text.trim() || optionalLists.some(([key]) => spec[key].some((item) => item.trim()));
  const optionalInvalid = issues.some(({ path }) => path === '/supplemental_text'
    || optionalLists.some(([key]) => path === '/' + key || path.startsWith('/' + key + '/')));

  return <div className="panel spec-form">
    <section className="spec-section" aria-labelledby="spec-overview">
      <div className="panel-title">
        <h2 id="spec-overview">产品概况</h2>
        {issues.length > 2 && <button className="spec-quiet" aria-pressed={showMissing}
          onClick={() => setShowMissing(!showMissing)}>{showMissing ? '隐藏必填提示' : '标示待填写项'}</button>}
      </div>
      <Field label="产品名称" error={error('/product_name', '产品名称')}><input maxLength={120} value={spec.product_name}
        placeholder="输入产品名称" onChange={(event) => setSpec({ ...spec, product_name: event.target.value })} /></Field>
      <Field label="产品背景" error={error('/background', '产品背景')}><textarea rows={2} maxLength={4000} value={spec.background}
        placeholder="描述要解决的问题" onChange={(event) => setSpec({ ...spec, background: event.target.value })} /></Field>
      <div className="spec-grid">{overviewLists.map(list)}</div>
    </section>

    <section className="spec-section" aria-labelledby="spec-requirements">
      <div className="panel-title">
        <div className="spec-section-title"><h2 id="spec-requirements">需求条目</h2>
          {spec.requirements.length > 0 && <span className="spec-count">{spec.requirements.length}</span>}</div>
        {spec.requirements.length > 0 && <button className="spec-add" disabled={spec.requirements.length >= 200} onClick={addRequirement}>添加需求</button>}
      </div>
      {spec.requirements.length === 0 && <div className="spec-requirements-empty">
        <p>添加至少一项需求，并写明如何验收。</p>
        <button className="spec-add" onClick={addRequirement}>添加需求</button>
      </div>}
      {spec.requirements.length > 0 && requirementIssue && <p className="spec-error">{requirementIssue.message}</p>}
      {spec.requirements.map((requirement, index) => {
        const path = '/requirements/' + index;
        return <div key={index} className="spec-requirement">
          <div className="spec-grid spec-requirement-meta">
            <Field label="需求 ID" error={error(path + '/id', '需求 ID')}><input value={requirement.id}
              onChange={(event) => update(index, { id: event.target.value })} /></Field>
            <Field label="类型" error={error(path + '/kind', '类型')}><select value={requirement.kind}
              onChange={(event) => update(index, { kind: event.target.value as Requirement['kind'] })}>
              <option value="functional">功能需求</option><option value="nonfunctional">非功能需求</option>
            </select></Field>
            <Field label="需求优先级" error={error(path + '/priority', '需求优先级')}><select value={requirement.priority}
              onChange={(event) => update(index, { priority: event.target.value as Requirement['priority'] })}>
              <option value="must">必须</option><option value="should">应该</option><option value="could">可选</option>
            </select></Field>
          </div>
          <Field label="需求描述" error={error(path + '/text', '需求描述')}><textarea rows={2} value={requirement.text}
            onChange={(event) => update(index, { text: event.target.value })} /></Field>
          <Lines label="需求验收标准" error={error(path + '/acceptance_criteria', '需求验收标准')} value={requirement.acceptance_criteria}
            onChange={(value) => update(index, { acceptance_criteria: value })} />
          <button className="spec-quiet danger" onClick={() => setSpec({ ...spec, requirements: spec.requirements.filter((_, i) => i !== index) })}>移除需求</button>
        </div>;
      })}
    </section>

    <section className="spec-section" aria-labelledby="spec-acceptance">
      <h2 id="spec-acceptance">交付与验收</h2>
      <div className="spec-grid">{acceptanceLists.map(list)}</div>
    </section>

    <details className="spec-options" open={optionalInvalid || undefined}>
      <summary>约束与补充说明 <span>{optionalInvalid ? '待修正' : hasOptional ? '可选 · 已填写' : '可选'}</span></summary>
      <div className="spec-options-fields">
        <div className="spec-grid">{optionalLists.map(list)}</div>
        <Field label="补充说明" error={error('/supplemental_text', '补充说明')}><textarea rows={2} maxLength={12000}
          value={spec.supplemental_text} onChange={(event) => setSpec({ ...spec, supplemental_text: event.target.value })} /></Field>
      </div>
    </details>
  </div>;
}

const advancedFields = ['inputs', 'assumptions', 'estimated_effort'] as const;
function AdvancedTask({ task, patch, readonly }: {
  task: Task; patch(value: Partial<Task>): void; readonly: boolean;
}) {
  const value = Object.fromEntries(advancedFields.map((field) => [field, task[field]]));
  const [buffer, setBuffer] = useState<string | null>(null);
  const [error, setError] = useState('');
  return <details><summary>输入绑定、假设与工时</summary>
    <Field label="高级字段 JSON"><textarea rows={8} spellCheck={false} readOnly={readonly}
      value={buffer ?? JSON.stringify(value, null, 2)} onChange={(event) => setBuffer(event.target.value)} /></Field>
    {!readonly && <button disabled={buffer === null} onClick={() => {
      try {
        const candidate = JSON.parse(buffer ?? '');
        if (!candidate || Object.keys(candidate).length !== advancedFields.length
          || !advancedFields.every((field) => Object.hasOwn(candidate, field))) throw new Error('请保留这三个字段');
        const problems = validatePlanStructure({ schema_version: '1.0', tasks: [{ ...task, ...candidate }], blocking_questions: [] })
          .filter(({ path }) => advancedFields.some((field) => path.startsWith('/tasks/0/' + field)));
        if (problems.length) throw new Error(problems.map(({ path, message }) => path + ' ' + message).join('；'));
        patch(candidate);
        setBuffer(null);
        setError('');
      } catch (err) { setError(err instanceof Error ? err.message : '无法读取高级字段'); }
    }}>应用高级字段</button>}
    {error && <p role="alert" className="error">{error}</p>}
  </details>;
}

export function TaskEditor({ task, tasks, readonly, patch, connect, disconnect, remove, close }: {
  task: Task; tasks: Task[]; readonly: boolean; patch(value: Partial<Task>): void;
  connect(source: string): void; disconnect(source: string): void; remove(): void; close(): void;
}) {
  const [upstream, setUpstream] = useState('');
  const heading = useId();
  const fields = [['name', '任务名称'], ['category', '类别'], ['stage', '阶段'], ['assigned_role', '建议角色']] as const;
  return <aside className="panel inspector" aria-labelledby={heading}>
    <div className="panel-title"><h2 id={heading}>任务详情</h2><button aria-label="关闭任务详情" onClick={close}>×</button></div>
    <code className="muted">{task.task_id}</code>
    <fieldset disabled={readonly}>
      {fields.map(([key, label]) => <Field key={key} label={label}><input value={task[key]}
        onChange={(event) => patch({ [key]: event.target.value })} /></Field>)}
      <Field label="任务描述"><textarea rows={3} value={task.description} onChange={(event) => patch({ description: event.target.value })} /></Field>
      <Field label="优先级"><select value={task.priority} onChange={(event) => patch({ priority: event.target.value as Task['priority'] })}>
        <option value="high">高</option><option value="medium">中</option><option value="low">低</option>
      </select></Field>
      <h3>上游依赖</h3>
      <ul className="dependency-list">{task.dependencies.map((id) => <li key={id}>
        <span>{tasks.find((item) => item.task_id === id)?.name || id}</span>
        {!readonly && <button aria-label={'移除依赖 ' + id} onClick={() => disconnect(id)}>移除</button>}
      </li>)}</ul>
      {!readonly && <div className="inline-form">
        <select aria-label="上游任务" value={upstream} onChange={(event) => setUpstream(event.target.value)}>
          <option value="">选择上游任务</option>
          {tasks.filter((item) => item.task_id !== task.task_id && !task.dependencies.includes(item.task_id)).map((item) =>
            <option key={item.task_id} value={item.task_id}>{item.name || item.task_id}</option>)}
        </select>
        <button disabled={!upstream} onClick={() => { connect(upstream); setUpstream(''); }}>添加依赖</button>
      </div>}
      <h3>交付物</h3>
      {task.deliverables.map((item, index) => <div key={index} className="deliverable">
        <Field label="交付 ID"><input value={item.id} onChange={(event) =>
          patch({ deliverables: task.deliverables.map((entry, i) => i === index ? { ...entry, id: event.target.value } : entry) })} /></Field>
        <Field label="交付内容"><input value={item.text} onChange={(event) =>
          patch({ deliverables: task.deliverables.map((entry, i) => i === index ? { ...entry, text: event.target.value } : entry) })} /></Field>
        {!readonly && <button onClick={() => patch({ deliverables: task.deliverables.filter((_, i) => i !== index) })}>移除交付物</button>}
      </div>)}
      {!readonly && <button onClick={() => patch({ deliverables: [...task.deliverables, { id: 'OUT_' + crypto.randomUUID().slice(0, 8), text: '' }] })}>添加交付物</button>}
      <Lines label="任务验收标准" value={task.acceptance_criteria} onChange={(value) => patch({ acceptance_criteria: value })} />
      <Lines label="关联需求 ID" value={task.source_requirement_ids} onChange={(value) => patch({ source_requirement_ids: value })} />
      <Field label="规划依据"><textarea value={task.rationale} onChange={(event) => patch({ rationale: event.target.value })} /></Field>
    </fieldset>
    <AdvancedTask task={task} patch={patch} readonly={readonly} />
    {!readonly && <button className="danger" onClick={remove}>删除任务</button>}
  </aside>;
}
