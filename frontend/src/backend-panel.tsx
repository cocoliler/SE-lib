import { useEffect, useRef, useState } from 'react';
import { ApiFailure, backendApi } from './api/client';
import type {
  Granularity, Layout as RemoteLayout, PlanDerivation, PlanRevision, PlanRevisionSummary, PlanningMode,
  PlanningPolicy, PlanningRun, Project as RemoteProject, SavePlanRequest, SpecRevision, TaskProposal,
} from './api/generated/contracts';
import { decodeLayout, encodeLayout } from './layout';
import { normalizeContractText, validateSpec } from './plan';
import { emptyLayout, type Project, type Workspace } from './storage';

type Binding = {
  projectId: string;
  planId?: string;
  origin?: { id: string; specId: string; policy: PlanningPolicy | null };
};
const statusLabels = {
  QUEUED: '排队中', RUNNING: '规划中', SUCCEEDED: '规划完成', NEEDS_INPUT: '需要补充信息', FAILED: '规划失败',
};

function readBinding(key: string): Binding | null {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null'); }
  catch { return null; }
}

export function BackendPanel({ project, update, publish }: {
  project: Project;
  update(apply: (workspace: Workspace) => Workspace): void;
  publish(value: { workspace: Workspace; result: PlanDerivation } | null): void;
}) {
  const workspace = project.workspace;
  const latest = useRef(workspace);
  latest.current = workspace;
  const storageKey = 'flowstudio.backend.v1.' + project.id;
  const [binding, setBinding] = useState(() => readBinding(storageKey));
  const [controller] = useState(() => new AbortController());
  const [api] = useState(() => backendApi(controller.signal));
  const [spec, setSpec] = useState<SpecRevision | null>(null);
  const [head, setHead] = useState<PlanRevisionSummary | null>(null);
  const [history, setHistory] = useState<PlanRevisionSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [viewed, setViewed] = useState<PlanRevision | null>(null);
  const [serverLayout, setServerLayout] = useState<RemoteLayout | null>(null);
  const [remoteProjects, setRemoteProjects] = useState<RemoteProject[] | null>(null);
  const [remoteCursor, setRemoteCursor] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [message, setMessage] = useState('');
  const [failure, setFailure] = useState('');
  const pendingKey = storageKey + '.pending';
  const [pending, setPending] = useState<string | null>(() => {
    try { return sessionStorage.getItem(pendingKey); }
    catch { return null; }
  });
  const [run, setRun] = useState<PlanningRun | null>(null);
  const [now, setNow] = useState(Date.now);
  const [candidate, setCandidate] = useState<{ specId: string; proposal: TaskProposal } | null>(null);
  const [mode, setMode] = useState<PlanningMode>('REAL');
  const [fixture, setFixture] = useState('diamond');
  const [granularity, setGranularity] = useState<Granularity>('standard');
  const [constraints, setConstraints] = useState('');
  const [policyText, setPolicyText] = useState('');
  const [confirmed, setConfirmed] = useState<{ tasks: Workspace['plan']['tasks']; ids: string[] } | null>(null);

  useEffect(() => () => controller.abort(), [controller]);
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pending]);

  function track(id: string | null) {
    setPending(id);
    try {
      if (id) sessionStorage.setItem(pendingKey, id);
      else sessionStorage.removeItem(pendingKey);
    } catch { /* Keep tracking in this page when session storage is unavailable. */ }
  }

  function remember(value: Binding) {
    setBinding(value);
    try { localStorage.setItem(storageKey, JSON.stringify(value)); }
    catch { throw new Error('服务端操作已完成，但浏览器无法保存项目关联。'); }
  }

  async function act(operation: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setFailure('');
    setMessage('');
    try { await operation(); }
    catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiFailure) {
        const { code, issues, request_id } = error.detail;
        const hint = code === 'REVISION_CONFLICT' ? '请比较服务端版本和本地草稿，再刷新版本信息。' : '';
        setFailure([error.message, ...issues.map((issue) => issue.path + ' ' + issue.message),
          hint, code + ' · 请求 ' + request_id].filter(Boolean).join('\n'));
      } else {
        setFailure(error instanceof TypeError ? '无法连接后端，请检查服务是否已启动。' :
          error instanceof Error ? error.message : '后端操作失败');
      }
    } finally {
      locked.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function refresh(target: Binding) {
    setReady(false);
    const [specs, revisions] = await Promise.all([
      api.specs(target.projectId),
      target.planId ? api.history(target.planId) : null,
    ]);
    const nextHead = revisions?.items[0] ?? null;
    setSpec(specs.items[0] ?? null);
    setHead(nextHead);
    setHistory(revisions?.items ?? []);
    setCursor(revisions?.next_cursor ?? null);
    setViewed(null);
    setServerLayout(null);
    publish(null);
    setReady(true);
  }

  const content = workspace.spec && normalizeContractText(workspace.spec);
  const specMatches = !!spec && !!content && equal(spec.content, content);
  const validSpec = !!content && !validateSpec(content).length;
  const origin = specMatches && binding?.origin?.specId === spec?.id && workspace.planningRunId === binding?.origin?.id ? binding?.origin : undefined;
  const assumptions = workspace.plan.tasks.flatMap((task) => task.assumptions.filter((item) => item.impact === 'low'));
  const confirmedIds = confirmed?.tasks === workspace.plan.tasks ? confirmed.ids : [];
  const planReady = ready && specMatches && workspace.plan.tasks.length > 0 && !workspace.plan.blocking_questions.length;

  function policy(): PlanningPolicy | null {
    if (!policyText.trim()) return null;
    try { return JSON.parse(policyText) as PlanningPolicy | null; }
    catch { throw new Error('规划策略须为有效的 JSON。'); }
  }

  async function saveSpec() {
    if (!binding || !content || !validSpec) return;
    if (specMatches) { setMessage('当前规格已保存到服务端。'); return; }
    setSpec(await api.saveSpec(binding.projectId, { expected_revision: spec?.revision ?? 0, content }));
    setCandidate(null);
    setRun(null);
    publish(null);
    setMessage('规格版本已保存。');
  }

  async function generate() {
    if (!spec || !specMatches) return;
    setCandidate(null);
    setRun(null);
    const created = await api.startRun({
      spec_revision_id: spec.id, mode, ...(mode === 'TEST' ? { fixture_id: fixture.trim() } : {}),
      config: { model: 'configured-default', granularity,
        planning_constraints: constraints.split('\n').map((line) => line.trim()).filter(Boolean), policy: policy() },
    });
    track(created.id);
    await followRun(created.id);
  }

  async function followRun(id: string) {
    const readStatus = async () => {
      try { return await api.run(id); }
      catch (error) {
        if (error instanceof ApiFailure && error.detail.code === 'NOT_FOUND') track(null);
        throw error;
      }
    };
    let next = await readStatus();
    while (next.status === 'QUEUED' || next.status === 'RUNNING') {
      setNow(Date.now());
      setRun(next);
      await new Promise<void>((resolve) => window.setTimeout(resolve, 1500));
      next = await readStatus();
    }
    setRun(next);
    if (next.status === 'SUCCEEDED') {
      const { tasks } = await api.tasks(next.id);
      setCandidate({ specId: next.spec_revision_id, proposal: { schema_version: '1.0', tasks, blocking_questions: [] } });
    }
    track(null);
  }

  function useCandidate() {
    if (!candidate || !run || !binding || !specMatches || candidate.specId !== spec?.id) return;
    update((previous) => ({ ...previous, plan: candidate.proposal, edited: false, orchestrated: false,
      source: null, planningRunId: run.id, layout: emptyLayout() }));
    remember({ ...binding, origin: { id: run.id, specId: candidate.specId, policy: run.config_snapshot.policy ?? null } });
    setCandidate(null);
    publish(null);
    setMessage('候选任务已载入。');
  }

  function planInput() {
    if (!spec || !planReady) throw new Error('请先保存当前规格，补全任务并处理阻断问题。');
    return { spec_revision_id: spec.id, tasks: normalizeContractText(workspace.plan).tasks,
      policy: origin ? origin.policy : policy() };
  }

  async function orchestrate() {
    const result = await api.orchestrate(planInput());
    if (latest.current.spec !== workspace.spec || latest.current.plan !== workspace.plan) {
      setMessage('草稿在编排期间发生变化，请重新编排。');
      return;
    }
    publish({ workspace, result });
    setMessage(result.validation_report.valid ? '服务端编排完成。' : '服务端发现校验问题。');
  }

  function layoutInput(revision: number) {
    const encoded = encodeLayout(workspace.layout);
    const taskIds = new Set(workspace.plan.tasks.map((task) => task.task_id));
    return { ...encoded, expected_revision: revision,
      positions: Object.fromEntries(Object.entries(encoded.positions).filter(([id]) => taskIds.has(id))),
      viewport: encoded.viewport ?? { x: 0, y: 0, zoom: 1 } };
  }

  async function savePlan() {
    if (!binding) return;
    const { expected_revision, ...layout } = layoutInput(0);
    const data: SavePlanRequest = { ...planInput(), planning_run_id: origin?.id,
      confirmed_assumption_ids: confirmedIds.map((id) => id.trim()),
      // The backend binds this initial layout to the newly created revision.
      layout: { ...layout, plan_revision_id: head?.id ?? binding.projectId, revision: expected_revision } };
    const revision = head
      ? await api.appendPlan(head.plan_id, { ...data, expected_revision: head.revision, parent_revision_id: head.id })
      : (await api.createPlan(binding.projectId, data)).revision;
    setHead(revision);
    setViewed(revision);
    setHistory((items) => [revision, ...items]);
    setServerLayout(null);
    remember({ ...binding, planId: revision.plan_id });
    setMessage('已保存服务端计划 v' + revision.revision + ' · ' + revision.source + ' / ' + revision.origin_mode);
    if (latest.current.spec === workspace.spec && latest.current.plan === workspace.plan) {
      publish({ workspace, result: { ...revision, input_hash: revision.validation_report.input_hash } });
    }
  }

  async function loadLayout() {
    if (!head) return;
    const [revision, layout] = await Promise.all([api.revision(head.id), api.layout(head.id)]);
    setViewed(revision);
    setServerLayout(layout);
    setMessage('已读取布局版本 ' + layout.revision + '。');
  }

  const tasksById = (tasks: Workspace['plan']['tasks']) =>
    Object.fromEntries(tasks.map((task) => [task.task_id, task]));
  const layoutMatches = !!specMatches && !!viewed && viewed.id === head?.id &&
    viewed.spec_revision_id === spec?.id && equal(tasksById(viewed.tasks), tasksById(normalizeContractText(workspace.plan).tasks));

  return <details className="panel backend-panel" onToggle={(event) => {
    if (event.currentTarget.open && binding && !ready && !failure) void act(() => refresh(binding));
  }}>
    <summary>后端工作区{binding && ready ? ' · 已连接' : ''}</summary>
    {failure && <p className="error backend-error" role="alert">{failure}</p>}
    {message && <p role="status">{message}</p>}
    <fieldset disabled={busy}>
      {!binding ? <div className="actions">
        <button onClick={() => void act(async () => {
          const created = await api.createProject(project.name);
          const target = { projectId: created.id };
          remember(target);
          await refresh(target);
        })}>创建同名服务端项目</button>
        <button onClick={() => void act(async () => {
          const result = await api.projects();
          setRemoteProjects(result.items);
          setRemoteCursor(result.next_cursor);
        })}>查看服务端项目</button>
        {remoteProjects && <select aria-label="关联已有服务端项目" value="" onChange={(event) => {
          const target = { projectId: event.target.value };
          void act(async () => { remember(target); await refresh(target); });
        }}>
          <option value="" disabled>{remoteProjects.length ? '关联已有服务端项目' : '服务端暂无项目'}</option>
          {remoteProjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>}
        {remoteCursor && <button onClick={() => void act(async () => {
          const result = await api.projects(remoteCursor);
          setRemoteProjects((items) => [...(items ?? []), ...result.items]);
          setRemoteCursor(result.next_cursor);
        })}>加载更多项目</button>}
      </div> : <>
        <div className="actions backend-spec">
          <span className="muted">{specMatches ? '规格 v' + spec?.revision + ' 已同步'
            : (ready ? '当前规格未同步' : '尚未读取服务端版本')}</span>
          {!specMatches && <button disabled={!ready || !validSpec} onClick={() => void act(saveSpec)}>保存规格版本</button>}
          {spec && !specMatches && <button onClick={() => {
            update((previous) => ({ ...previous, spec: spec.content, edited: true, orchestrated: false }));
            publish(null);
          }}>载入服务端规格 v{spec.revision}</button>}

        </div>
        <div className="actions">
          <label>规划模式 <select value={mode} onChange={(event) => setMode(event.target.value as PlanningMode)}>
            <option value="REAL">真实模型</option><option value="TEST">测试样例</option>
          </select></label>
          {mode === 'TEST' && <label>样例 ID <input value={fixture} onChange={(event) => setFixture(event.target.value)} /></label>}
          <button className="primary" disabled={!!pending || !ready || !specMatches || (mode === 'TEST' && !fixture.trim())}
            onClick={() => void act(generate)}>发起规划</button>
          {pending && !busy && <button onClick={() => void act(() => followRun(pending))}>继续查询规划结果</button>}
        </div>
        <details className="backend-section">
          <summary>规划设置</summary>
          <label>任务粒度 <select value={granularity} onChange={(event) => setGranularity(event.target.value as Granularity)}>
            <option value="coarse">粗略</option><option value="standard">标准</option><option value="fine">细致</option>
          </select></label>
          <label>额外约束（每行一项）<textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} /></label>
          <label>规划策略 JSON<textarea value={policyText} onChange={(event) => {
            setPolicyText(event.target.value);
            publish(null);
          }} /></label>
          {origin && <p>当前候选任务使用其规划运行的策略快照。</p>}
        </details>
        {run && <div className="backend-run" role="status">
          <p>{statusLabels[run.status]} · {run.mode}
            {pending && (run.status === 'RUNNING' || run.status === 'QUEUED')
              ? ' · 已等待 ' + Math.max(0, Math.floor((now - Date.parse(run.created_at)) / 1000)) + ' 秒'
              : ' · ' + run.attempt_count + ' 次尝试'}
          </p>
          {run.error && <p>{run.error.code} · {run.error.message}</p>}
          {run.proposal?.blocking_questions.map((question, index) => <p key={index}>{question}</p>)}
          {run.validation_report?.errors.map((issue, index) => <p key={index}>{issue.path} {issue.message}</p>)}
          {candidate && <button disabled={!specMatches || candidate.specId !== spec?.id}
            onClick={() => void act(async () => useCandidate())}>用 {candidate.proposal.tasks.length} 项候选任务替换当前草稿</button>}
        </div>}
        {assumptions.length > 0 && <details className="backend-section backend-assumptions">
          <summary>确认假设 <span className="muted">{confirmedIds.length} / {assumptions.length}</span></summary>
          {assumptions.map((item, index) => <label className="backend-assumption" key={index}>
            <input type="checkbox" checked={confirmedIds.includes(item.id)} onChange={(event) =>
              setConfirmed({ tasks: workspace.plan.tasks, ids: event.target.checked
                ? [...confirmedIds, item.id] : confirmedIds.filter((id) => id !== item.id) })} />
            <span><strong>{item.id}</strong> · {item.text}</span>
          </label>)}
        </details>}
        <div className="actions backend-plan-actions">
          <button disabled={!planReady} onClick={() => void act(orchestrate)}>服务端编排</button>
          <button disabled={!planReady || assumptions.some((item) => !confirmedIds.includes(item.id))}
            onClick={() => void act(savePlan)}>保存计划版本</button>
        </div>
        <details className="backend-section backend-versions">
          <summary>版本与布局 {head && <span className="muted">v{head.revision}</span>}</summary>
          <div className="actions">
            <button onClick={() => void act(() => refresh(binding))}>刷新服务端版本</button>
            {head && <button onClick={() => void act(loadLayout)}>读取服务端布局</button>}
            {layoutMatches && serverLayout && <>
              <button onClick={() => {
                const layout = decodeLayout(serverLayout);
                if (layout) update((previous) => ({ ...previous, layout }));
              }}>应用服务端布局</button>
              <button onClick={() => void act(async () => {
                setServerLayout(await api.saveLayout(serverLayout.plan_revision_id, layoutInput(serverLayout.revision)));
                setMessage('布局已保存。');
              })}>保存布局</button>
            </>}
          </div>
          {history.length > 0 && <div className="actions">
            <select aria-label="服务端计划历史" value={viewed?.id ?? ''} onChange={(event) => {
              const id = event.target.value;
              void act(async () => { setViewed(await api.revision(id)); });
            }}>
              <option value="" disabled>查看计划版本</option>
              {history.map((item) => <option key={item.id} value={item.id}>v{item.revision} · {item.source}</option>)}
            </select>
            {cursor && binding.planId && <button onClick={() => void act(async () => {
              const result = await api.history(binding.planId!, cursor);
              setHistory((items) => [...items, ...result.items]);
              setCursor(result.next_cursor);
            })}>加载更多版本</button>}
            {viewed && <a href={'/api/v1/plan-revisions/' + viewed.id + '/export?format=json'}>导出完整计划包 v{viewed.revision}</a>}
          </div>}
          {viewed && <details>
            <summary>v{viewed.revision} · {viewed.source} / {viewed.origin_mode} · {viewed.tasks.length} 项任务</summary>
            <ol>{viewed.ordered_task_ids.map((id) => <li key={id}>{viewed.tasks.find((task) => task.task_id === id)?.name ?? id}</li>)}</ol>
          </details>}
        </details>
      </>}
    </fieldset>
    {busy && <p role="status">{pending ? '正在查询规划结果，刷新后可继续查询同一请求。' : '正在与后端通信…'}</p>}
  </details>;
}

function equal(left: unknown, right: unknown): boolean {
  function stable(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(stable);
    if (value && typeof value === 'object') {
      const object = value as Record<string, unknown>;
      return Object.fromEntries(Object.keys(object).sort().map((key) => [key, stable(object[key])]));
    }
    return value;
  }
  return JSON.stringify(stable(left)) === JSON.stringify(stable(right));
}
