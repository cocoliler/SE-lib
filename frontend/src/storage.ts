import { emptyPlan, isWorkspaceDraft, type Plan, type Source, type Spec } from './plan';

import { decodeLayout, encodeLayout, type Layout, type StoredLayout } from './layout';
export type { Layout, Point } from './layout';

export type Workspace = {
  spec: Spec | null;
  plan: Plan;
  source: Source | null;
  edited: boolean;
  orchestrated: boolean;
  planningRunId?: string;
  layout: Layout;
};
export type Snapshot = { id: string; at: string; workspace: Workspace };
export type Project = { id: string; name: string; workspace: Workspace; history: Snapshot[] };

const key = 'flowstudio.workspace.v1';
export const emptyLayout = (): Layout => ({ positions: {}, notes: [] });
export function createProject(name: string): Project {
  return {
    id: crypto.randomUUID(), name, history: [],
    workspace: { spec: null, plan: emptyPlan(), source: null, edited: false, orchestrated: false, layout: emptyLayout() },
  };
}

export function readProjects(storage: Pick<Storage, 'getItem'>): Project[] {
  const raw = storage.getItem(key);
  if (raw === null) return [];
  const data = JSON.parse(raw);
  type StoredWorkspace = Omit<Workspace, 'layout'> & { layout: Layout | StoredLayout };
  type StoredSnapshot = Omit<Snapshot, 'workspace'> & { workspace: StoredWorkspace };
  type StoredProject = Omit<Project, 'workspace' | 'history'> & { workspace: StoredWorkspace; history: StoredSnapshot[] };

  function parseWorkspace(workspace: StoredWorkspace): Workspace {
    const layout = decodeLayout(workspace?.layout);
    if (!layout || !isWorkspaceDraft(workspace.spec, workspace.plan)
      || ![null, 'MANUAL', 'IMPORTED', 'PRESET'].includes(workspace.source)
      || (workspace.planningRunId !== undefined && typeof workspace.planningRunId !== 'string')
      || typeof workspace.edited !== 'boolean' || typeof workspace.orchestrated !== 'boolean') {
      throw new Error('浏览器存储格式无法读取');
    }
    return { ...workspace, layout };
  }

  if (!Array.isArray(data)) throw new Error('浏览器存储格式无法读取');
  return data.map((item: StoredProject) => {
    if (typeof item?.id !== 'string' || typeof item?.name !== 'string' || !Array.isArray(item.history)) {
      throw new Error('浏览器存储格式无法读取');
    }
    const history = item.history.map((entry) => {
      if (typeof entry?.id !== 'string' || !Number.isFinite(Date.parse(entry.at))) {
        throw new Error('浏览器存储格式无法读取');
      }
      return { ...entry, workspace: parseWorkspace(entry.workspace) };
    });
    return { ...item, workspace: parseWorkspace(item.workspace), history };
  });
}

export function writeProjects(storage: Pick<Storage, 'setItem'>, projects: Project[]) {
  const encodeWorkspace = (workspace: Workspace) => ({ ...workspace, layout: encodeLayout(workspace.layout) });
  storage.setItem(key, JSON.stringify(projects.map((project) => ({
    ...project,
    workspace: encodeWorkspace(project.workspace),
    history: project.history.map((entry) => ({ ...entry, workspace: encodeWorkspace(entry.workspace) })),
  }))));
}

export function snapshot(project: Project): Project {
  const previous = project.history[0];
  if (previous && JSON.stringify(previous.workspace) === JSON.stringify(project.workspace)) return project;
  return {
    ...project,
    history: [{ id: crypto.randomUUID(), at: new Date().toISOString(), workspace: structuredClone(project.workspace) },
      ...project.history].slice(0, 30),
  };
}

function rejectDuplicateKeys(json: string) {
  const scopes: (Set<string> | null)[] = [];
  const tokens = /"(?:[^"\\]|\\[\s\S])*"|[{}\[\]:]/g;
  let previous = '';
  for (const [token] of json.matchAll(tokens)) {
    if (token === '{') scopes.push(new Set());
    else if (token === '[') scopes.push(null);
    else if (token === '}' || token === ']') scopes.pop();
    else if (token === ':') {
      // JSON syntax has already been checked, so the preceding token is an object key.
      const keys = scopes.at(-1)!;
      const key: string = JSON.parse(previous);
      if (keys.has(key)) throw new Error('JSON 包含重复键：' + JSON.stringify(key));
      keys.add(key);
    }
    previous = token;
  }
}

export async function readJson(file: File): Promise<unknown> {
  if (file.size > 1024 * 1024) throw new Error('JSON 文件不得超过 1 MiB');
  let text: string;
  let value: unknown;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
    value = JSON.parse(text);
  } catch {
    throw new Error('无法读取 JSON，请检查文件格式和 UTF-8 编码');
  }
  rejectDuplicateKeys(text);
  return value;
}

export function downloadJson(filename: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
