import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { WorkflowCanvas } from './canvas';
import { Field, Issues, Lines, SpecEditor, TaskEditor } from './forms';
import {
  assessPlan, emptySpec, linkError, newTask, planState, removeTask, validatePlanStructure, validateSpec,
  type Issue, type Plan, type Spec, type Task,
} from './plan';
import {
  createProject, downloadJson, emptyLayout, readJson, readProjects, snapshot, writeProjects,
  type Project, type Snapshot, type Workspace,
} from './storage';
import { createMeetingRoomProject, meetingRoomPresetName } from './presets';
import { BatchPanel, ImportPreview, TaskNavigator, type ImportCandidate } from './workspace-panels';
import './style.css';

const sourceLabels = { MANUAL: 'MANUAL · 手动', IMPORTED: 'IMPORTED · 导入', PRESET: 'PRESET · 预设' };
const stateLabels = {
  NO_PLAN: '暂无任务', PLAN_INVALID: '计划有校验问题', PLAN_VALID: '编排有效',
  REORCHESTRATION_REQUIRED: '待重新编排', PLAN_AVAILABLE: '任务已就绪',
};
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <section className="empty"><h2>{title}</h2>{children}</section>;
}

function App() {
  const [initial] = useState(() => {
    try { return { projects: readProjects(localStorage), error: '' }; }
    catch { return { projects: [], error: '无法读取浏览器中的项目。原有数据已保留，请检查浏览器存储。' }; }
  });
  const [projects, setProjects] = useState(initial.projects);
  const [active, setActive] = useState<string | null>(() => initial.projects[0]?.id ?? null);
  const [unsaved, setUnsaved] = useState<Set<string>>(() => new Set());
  const [creating, setCreating] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try { return localStorage.getItem('flowstudio.theme') === 'dark' ? 'dark' : 'light'; }
    catch { return 'light'; }
  });
  const [name, setName] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState(initial.error);
  const project = projects.find((item) => item.id === active);

  useEffect(() => {
    if (!unsaved.size) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = true; };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [unsaved.size]);

  function save(next: Project[], message: string) {
    if (initial.error) return false;
    try {
      writeProjects(localStorage, next);
      setProjects(next);
      setUnsaved(new Set());
      setError('');
      setNotice(message);
      return true;
    } catch {
      setError('无法保存到此浏览器。请检查存储权限或剩余空间，当前编辑仍保留在页面上。');
      return false;
    }
  }

  function addProject(next: Project) {
    if (!save([...projects, next], next.name + '已保存到此浏览器')) return;
    setActive(next.id);
    setName('');
    setCreating(false);
  }

  function add(event: FormEvent) {
    event.preventDefault();
    if (name.trim()) addProject(createProject(name.trim()));
  }

  const createExample = () => addProject(createMeetingRoomProject(projects));

  function update(id: string, apply: (current: Workspace) => Workspace) {
    setProjects((items) => items.map((item) => item.id === id ? { ...item, workspace: apply(item.workspace) } : item));
    setUnsaved((current) => current.has(id) ? current : new Set([...current, id]));
  }

  function toggleTheme() {
    const next = theme === 'light' ? 'dark' : 'light';
    setTheme(next);
    try { localStorage.setItem('flowstudio.theme', next); } catch { /* Keep the theme for this session. */ }
  }

  return <div className="application" data-theme={theme}>
    <header className="app-header">
      <button className="brand" onClick={() => { setActive(null); setNotice(''); }}>
        <span className="brand-mark" aria-hidden="true">↳</span>FlowStudio <small>v3.1</small>
      </button>
      <span className="header-divider" />
      {projects.length ? <select className="project-picker" aria-label="切换项目" value={project?.id ?? ''} onChange={(event) => {
        setActive(event.target.value || null); setCreating(false); setNotice('');
      }}>
        <option value="">项目工作台</option>
        {projects.map((item) => <option key={item.id} value={item.id}>
          {item.name}{unsaved.has(item.id) ? ' •' : ''}
        </option>)}
      </select> : <span className="app-context">项目工作台</span>}
      <button className="new-project" aria-label="新建项目" title="新建项目" onClick={() => setCreating(!creating)} disabled={!!initial.error}>＋</button>
      <div className="header-actions">
        {project && <><span className="local-label"><i />{unsaved.has(project.id) ? '有改动尚未保存' : '浏览器本地'}</span>
        <button onClick={() => save(projects.map((item) => item.id === project.id ? snapshot(item) : item),
          '已保存到此浏览器并记录快照')}>保存快照</button>
        <button className="primary" onClick={() => save(projects, '改动已保存到此浏览器')}>保存到浏览器</button></>}
        <button className="theme-switch" aria-pressed={theme === 'dark'} aria-label="深色外观" title="切换深色外观" onClick={toggleTheme}>{theme === 'dark' ? '☀' : '☾'}</button>
      </div>
    </header>
    <main className="main">
      {error && <p className="error banner" role="alert">{error}</p>}
      {creating && <form className="project-form" onSubmit={add}>
        <Field label="项目名称"><input autoFocus required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></Field>
        <div className="actions"><button className="primary" type="submit">创建</button>
          <button type="button" title={meetingRoomPresetName} onClick={createExample}>从示例创建</button>
          <button type="button" onClick={() => setCreating(false)}>取消</button></div>
      </form>}
      {project ? <ProjectView key={project.id} project={project} theme={theme} update={(apply) => update(project.id, apply)} notice={setNotice} />
        : <div className="page landing">
          <section className="panel start-panel">
            <span className="brand-mark" aria-hidden="true">↳</span>
            <h1>项目工作台</h1>
            <p className="muted">{projects.length ? '从顶栏打开项目，或创建新项目。' : '暂无项目。创建项目后即可填写规格和编排任务。'}</p>
            {!creating && <div className="actions">
              <button className="primary" disabled={!!initial.error} onClick={() => setCreating(true)}>创建项目</button>
              <button disabled={!!initial.error} title={meetingRoomPresetName} onClick={createExample}>从示例创建</button>
            </div>}
            <ol className="start-flow" aria-label="项目流程"><li>设计规格</li><li>任务规划</li><li>工作流</li></ol>
          </section>
        </div>}
    </main>
    <footer className="app-footer"><span>FlowStudio v3.1</span><span role="status">{notice}</span></footer>
  </div>;
}

function ProjectView({ project, theme, update, notice }: {
  project: Project; theme: 'light' | 'dark'; update(apply: (workspace: Workspace) => Workspace): void;
  notice(message: string): void;
}) {
  const [tab, setTab] = useState<'spec' | 'plan' | 'history'>('spec');
  const [view, setView] = useState<'list' | 'canvas'>('list');
  const [showNavigator, setShowNavigator] = useState(() => window.matchMedia('(min-width: 1180px)').matches);
  const [locateRequest, setLocateRequest] = useState<{ id: string } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [history, setHistory] = useState<Snapshot | null>(null);
  const [candidate, setCandidate] = useState<ImportCandidate | null>(null);
  const [importIssues, setImportIssues] = useState<Issue[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const importType = useRef<'spec' | 'plan'>('spec');
  const fileRequest = useRef(0);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const workspace = history?.workspace ?? project.workspace;
  const { spec, plan, layout, source, edited, orchestrated } = workspace;
  const specDraft = useMemo(() => spec ?? emptySpec(), [spec]);
  const specIssues = useMemo(() => spec ? validateSpec(spec) : [], [spec]);
  const ready = !!spec && !specIssues.length;
  const assessment = useMemo(() => assessPlan(plan, specDraft), [plan, specDraft]);
  const state = planState(plan, assessment, orchestrated && ready && !!assessment.result, edited);
  const current = state === 'PLAN_VALID' ? assessment.result : undefined;
  const task = plan.tasks.find((item) => item.task_id === selected);
  const readonly = !!history;

  function navigate(next: typeof tab) {
    fileRequest.current++;
    setCandidate(null);
    setImportIssues([]);
    setHistory(null);
    setSelected(null);
    setDeleting(null);
    setTab(next);
    setLocateRequest(null);
  }

  function select(id: string | null) {
    if (id && !selected && document.activeElement instanceof HTMLElement) lastTrigger.current = document.activeElement;
    setSelected(id);
    setDeleting(null);
  }

  function closeDetails() {
    setLocateRequest(null);
    select(null);
    lastTrigger.current?.focus();
  }

  function changeSpec(next: Spec) {
    update((previous) => ({ ...previous, spec: next, edited: previous.plan.tasks.length > 0 || previous.edited, orchestrated: false }));
  }

  function changePlan(apply: (plan: Plan) => Plan) {
    update((previous) => ({
      ...previous, plan: apply(previous.plan), source: 'MANUAL', orchestrated: false, edited: true,
    }));
  }

  function patch(id: string, fields: Partial<Task>) {
    changePlan((previous) => ({ ...previous, tasks: previous.tasks.map((item) => item.task_id === id ? { ...item, ...fields } : item) }));
  }

  function addTask() {
    if (plan.tasks.length >= 100) { notice('每份计划最多包含 100 项任务'); return; }
    const id = 'task_' + crypto.randomUUID().replaceAll('-', '');
    update((previous) => ({
      ...previous, plan: { ...previous.plan, tasks: [...previous.plan.tasks, newTask(id)] }, source: 'MANUAL',
      orchestrated: false, edited: previous.plan.tasks.length > 0 || previous.edited,
    }));
    select(id);
    notice('已添加空白任务，请填写任务字段');
  }

  function connect(upstream: string, target: string) {
    const error = linkError(plan, upstream, target);
    if (error) { notice(error); return; }
    const destination = plan.tasks.find((item) => item.task_id === target);
    if (!destination) return;
    patch(target, { dependencies: [...destination.dependencies, upstream] });
    notice('已添加上游依赖');
  }

  function remove(id: string) {
    update((previous) => ({
      ...previous, plan: removeTask(previous.plan, id), source: 'MANUAL', edited: true, orchestrated: false,
      layout: { ...previous.layout, positions: Object.fromEntries(Object.entries(previous.layout.positions).filter(([key]) => key !== id)) },
    }));
    closeDetails();
    notice('任务及引用关系已删除');
  }

  function reorchestrate() {
    if (!assessment.result || !ready) { notice('请先解决校验问题'); return; }
    update((previous) => ({ ...previous, orchestrated: true, edited: false }));
    notice('本地编排完成，共 ' + assessment.result.batches.length + ' 个并行批次');
  }

  function pick(kind: 'spec' | 'plan') {
    importType.current = kind;
    fileInput.current?.click();
  }

  async function load(file: File) {
    const kind = importType.current;
    const request = ++fileRequest.current;
    setCandidate(null);
    setImportIssues([]);
    try {
      const value = await readJson(file);
      if (request !== fileRequest.current) return;
      const issues = kind === 'spec' ? validateSpec(value) : validatePlanStructure(value);
      if (issues.length) { setImportIssues(issues); return; }
      if (kind === 'spec') setCandidate({ kind, filename: file.name, value: value as Spec, issues: [] });
      else {
        const imported = value as Plan;
        const ids = imported.tasks.map(({ task_id }) => task_id);
        if (new Set(ids).size !== ids.length) {
          setImportIssues([{ path: '/tasks', message: '任务 ID 重复，请在 JSON 中修正后重新导入' }]);
          return;
        }
        const analysis = assessPlan(imported, specDraft);
        setCandidate({ kind, filename: file.name, value: imported, issues: analysis.issues, result: analysis.result });
      }
    } catch (error) {
      if (request === fileRequest.current) setImportIssues([{ path: '/', message: error instanceof Error ? error.message : '读取失败' }]);
    }
  }

  function applyImport() {
    if (!candidate) return;
    if (candidate.kind === 'spec') changeSpec(candidate.value);
    else {
      const value = candidate.value;
      update((previous) => ({
        ...previous, plan: value, source: 'IMPORTED', edited: false, orchestrated: false,
        layout: { ...emptyLayout(), notes: previous.layout.notes.filter((note) => !value.tasks.some((item) => item.task_id === note.id)) },
      }));
      setSelected(null);
    }
    setCandidate(null);
    notice('JSON 已导入，请保存到此浏览器');
  }

  const viewingPlan = tab === 'plan' || (tab === 'history' && !!history);
  const canExportPlan = (plan.tasks.length > 0 || plan.blocking_questions.length > 0) && !validatePlanStructure(plan).length;

  return <div className={tab === 'spec' ? 'page project-page spec-page' : 'page project-page'} onKeyDown={(event) => {
    if (event.key === 'Escape' && selected) { event.stopPropagation(); closeDetails(); }
  }}>
    <nav className="tabs" aria-label="项目工作区">
      <button aria-current={tab === 'spec' ? 'page' : undefined} onClick={() => navigate('spec')}>设计规格</button>
      <button aria-current={tab === 'plan' ? 'page' : undefined} disabled={!project.workspace.spec || !!validateSpec(project.workspace.spec).length}
        onClick={() => navigate('plan')}>任务规划</button>
      <button aria-current={tab === 'history' ? 'page' : undefined} onClick={() => navigate('history')}>本地历史</button>
    </nav>
    <input ref={fileInput} type="file" accept=".json,application/json" hidden onChange={(event) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (file) void load(file);
    }} />
    <Issues issues={importIssues} />
    {candidate && <ImportPreview candidate={candidate} apply={applyImport} cancel={() => setCandidate(null)} />}
    {tab === 'spec' && !candidate && <>
      <header className="spec-heading">
        <div>
          <h1>设计规格</h1>
          <p className={'spec-status' + (ready ? ' ready' : '')} role="status">{ready ? '规格已通过基础校验'
            : spec ? '规格草稿 · ' + specIssues.length + ' 项待完善' : '空项目 · 尚无设计规格'}</p>
        </div>
        <div className="actions spec-actions">
          <button className="spec-quiet" onClick={() => pick('spec')}>导入规格 JSON</button>
          {spec && <button className="spec-quiet" onClick={() => downloadJson('design-spec.json', spec)} disabled={!ready}>导出规格 JSON</button>}
          {ready && <button className="primary" onClick={() => navigate('plan')}>进入任务规划</button>}
        </div>
      </header>
      {spec ? <SpecEditor spec={spec} issues={specIssues} setSpec={changeSpec} />
        : <Empty title="添加设计规格">
          <p>填写产品目标、需求和验收标准，或导入现有规格。</p>
          <button className="primary" onClick={() => changeSpec(emptySpec())}>填写规格</button>
        </Empty>}
    </>}
    {tab === 'history' && <section className="panel history">
      <div className="panel-title"><h2>本地历史</h2><span className="muted">保留最近 30 个快照</span></div>
      {!project.history.length && <p className="muted">暂无快照。使用「保存快照」记录当前规格、任务和布局。</p>}
      {project.history.map((entry) => <button key={entry.id} aria-pressed={history?.id === entry.id} onClick={() => {
        setHistory(entry); select(null);
      }}>{new Date(entry.at).toLocaleString('zh-CN')} · {entry.workspace.plan.tasks.length} 项任务</button>)}
      {history && <p className="muted">只读快照 · {history.workspace.spec?.product_name || '无产品规格'}</p>}
    </section>}
    {viewingPlan && !candidate && <>
      <section className="workspace-heading">
        <div><h1>{readonly ? '历史计划' : view === 'canvas' ? '工作流画布' : '任务规划'}</h1><p className="muted">{readonly ? '历史仅供查看和导出' : 'PM Agent 服务未连接'}</p></div>
        <div className="actions">
          {!readonly && <button onClick={() => pick('plan')}>导入任务 JSON</button>}
          <button onClick={() => downloadJson('task-plan.json', plan)} disabled={!canExportPlan}>导出任务 JSON</button>
          {readonly && ready && <button onClick={() => downloadJson('design-spec.json', spec)}>导出快照规格</button>}
          {!readonly && view === 'list' && plan.tasks.length > 0 && <button className="primary" onClick={addTask} disabled={plan.tasks.length >= 100}>手动创建任务</button>}
        </div>
      </section>
      <div className="plan-bar">
        <div className="switcher" role="group" aria-label="计划视图">
          <button aria-pressed={view === 'list'} onClick={() => { setLocateRequest(null); setView('list'); }}>任务列表</button>
          <button aria-pressed={view === 'canvas'} onClick={() => { setLocateRequest(null); setView('canvas'); }}>工作流</button>
        </div>
        {view === 'canvas' && plan.tasks.length > 0 && <button className="navigator-toggle" aria-pressed={showNavigator} onClick={() => setShowNavigator(!showNavigator)}>任务索引</button>}
        {state !== 'NO_PLAN' && <span className={'badge ' + state.toLowerCase()}>{stateLabels[state]}</span>}
        {source && <span className="badge" title={source}>{sourceLabels[source]}</span>}
        {plan.tasks.length > 0 && <span className="muted">{plan.tasks.length} 项任务</span>}
        {!readonly && plan.tasks.length > 0 && <button className="reorchestrate" onClick={reorchestrate} disabled={!assessment.result || !ready}>重新编排</button>}
      </div>
      {!readonly && plan.blocking_questions.length > 0 && <section className="panel form-panel">
        <h3>待处理问题</h3>
        <p className="muted">处理后可移除对应条目，再重新编排。</p>
        <Lines label="阻断问题" value={plan.blocking_questions} onChange={(questions) => changePlan((previous) =>
          ({ ...previous, blocking_questions: questions }))} />
      </section>}
      <Issues issues={assessment.issues} focus={(index) => select(plan.tasks[index]?.task_id ?? null)} />

      <div className={'plan-grid' + (task ? ' inspecting' : '') + (view === 'canvas' && showNavigator && plan.tasks.length ? ' with-navigator' : '')}>
        {view === 'canvas' && showNavigator && plan.tasks.length > 0 && <TaskNavigator tasks={plan.tasks} result={current}
          selected={selected} locate={(id) => { select(id); setLocateRequest({ id }); }} />}
        {view === 'canvas' ? <WorkflowCanvas key={history?.id ?? 'current'} plan={plan} layout={layout} readonly={readonly} theme={theme}
          batches={current?.batches} locateRequest={locateRequest}
          selected={selected} select={select} setLayout={(apply) => update((previous) => ({ ...previous, layout: apply(previous.layout) }))}
          addTask={addTask} connect={connect} notice={notice} /> : plan.tasks.length
          ? <section className="panel task-table" aria-label="任务列表"><table>
            <thead><tr><th>任务</th><th>阶段</th><th>建议角色</th><th>上游</th></tr></thead>
            <tbody>{plan.tasks.map((item) => <tr key={item.task_id} className={item.task_id === selected ? 'selected' : ''}>
              <td><button className="link" aria-pressed={item.task_id === selected} onClick={() => select(item.task_id)}>
                {item.name || '未命名任务'}</button><code>{item.task_id}</code></td>
              <td>{item.stage || '—'}</td><td>{item.assigned_role || '—'}</td><td>{item.dependencies.length}</td>
            </tr>)}</tbody>
          </table></section> : <Empty title="暂无任务规划">
            <p>{readonly ? '此快照未包含任务。' : '从手动创建任务开始，或导入已有计划。'}</p>
            {!readonly && <button className="primary" onClick={addTask}>创建首个任务</button>}
          </Empty>}
        {task && <div className="task-detail-column">
          <TaskEditor key={task.task_id + (history?.id ?? '')} task={task} tasks={plan.tasks} readonly={readonly}
            patch={(fields) => patch(task.task_id, fields)} connect={(upstream) => connect(upstream, task.task_id)}
            disconnect={(id) => {
              const linked = task.inputs.filter((input) => input.kind === 'task' && input.task_id === id).length;
              if (linked && !window.confirm('移除这条依赖将同时移除 ' + linked + ' 个输入绑定，继续？')) return;
              patch(task.task_id, { dependencies: task.dependencies.filter((item) => item !== id),
                inputs: task.inputs.filter((input) => input.kind !== 'task' || input.task_id !== id) });
            }} remove={() => setDeleting(task.task_id)} close={closeDetails} />
          {deleting === task.task_id && <section className="panel confirm" aria-label="确认删除任务">
            <p>将移除任务及 {plan.tasks.filter((item) => item.dependencies.includes(task.task_id)).length} 项任务对它的依赖，以及相关输入绑定。</p>
            <div className="actions"><button className="danger" onClick={() => remove(task.task_id)}>确认删除</button>
              <button onClick={() => setDeleting(null)}>取消</button></div>
          </section>}
        </div>}
      </div>
      {current && <BatchPanel result={current} tasks={plan.tasks} select={select} />}
    </>}
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);
