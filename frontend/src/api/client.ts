import type {
  CreatePlanningRunRequest, ErrorEnvelope, Layout, LayoutWriteRequest, OrchestrationRequest,
  PlanDerivation, PlanRevision, PlanRevisionSummaryPage, PlanningRun, PlanningRunCreated,
  PlanningRunTasksResponse, Project, ProjectPage, SavePlanRequest, SavePlanResponse,
  SavePlanRevisionRequest, SpecRevision, SpecRevisionPage, SpecRevisionWriteRequest,
} from './generated/contracts';

export class ApiFailure extends Error {
  constructor(readonly detail: ErrorEnvelope['error']) {
    super(detail.message);
  }
}

export function backendApi(signal: AbortSignal) {
  // A retry after a lost response must reuse the original command key.
  const keys = new Map<string, string>();

  async function request<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
    const body = data === undefined ? undefined : JSON.stringify(data);
    const headers: Record<string, string> = { Accept: 'application/json' };
    const command = method + ' ' + path + '\n' + body;
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      const key = keys.get(command) ?? crypto.randomUUID();
      keys.set(command, key);
      headers['Idempotency-Key'] = key;
    }
    const response = await fetch('/api/v1' + path, {
      method, body, headers, signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]),
    });
    const json = response.headers.get('content-type')?.includes('application/json')
      ? await response.json() : null;
    if (!response.ok || json === null) {
      if (response.status < 500 || json?.error) keys.delete(command);
      if (json?.error) throw new ApiFailure(json.error);
      throw new Error('无法读取后端响应（HTTP ' + response.status + '），请检查服务是否已启动。');
    }
    keys.delete(command);
    return json as T;
  }

  return {
    projects: (cursor?: string) => request<ProjectPage>('/projects' + page(cursor)),
    createProject: (name: string) => request<Project>('/projects', 'POST', { name }),
    specs: (id: string) => request<SpecRevisionPage>('/projects/' + id + '/spec-revisions?limit=1'),
    saveSpec: (id: string, data: SpecRevisionWriteRequest) =>
      request<SpecRevision>('/projects/' + id + '/spec-revisions', 'POST', data),
    startRun: (data: CreatePlanningRunRequest) => request<PlanningRunCreated>('/planning-runs', 'POST', data),
    run: (id: string) => request<PlanningRun>('/planning-runs/' + id),
    tasks: (id: string) => request<PlanningRunTasksResponse>('/planning-runs/' + id + '/tasks'),
    orchestrate: (data: OrchestrationRequest) => request<PlanDerivation>('/orchestrations', 'POST', data),
    createPlan: (id: string, data: SavePlanRequest) =>
      request<SavePlanResponse>('/projects/' + id + '/plans', 'POST', data),
    appendPlan: (id: string, data: SavePlanRevisionRequest) =>
      request<PlanRevision>('/plans/' + id + '/revisions', 'POST', data),
    history: (id: string, cursor?: string) => request<PlanRevisionSummaryPage>('/plans/' + id + '/revisions' + page(cursor)),
    revision: (id: string) => request<PlanRevision>('/plan-revisions/' + id),
    layout: (id: string) => request<Layout>('/plan-revisions/' + id + '/layout'),
    saveLayout: (id: string, data: LayoutWriteRequest) =>
      request<Layout>('/plan-revisions/' + id + '/layout', 'PUT', data),
  };
}

function page(cursor?: string) {
  return cursor ? '?cursor=' + encodeURIComponent(cursor) : '';
}
