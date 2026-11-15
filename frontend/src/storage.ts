import { emptyPlan, isWorkspaceDraft, type Plan, type Source, type Spec } from './plan';

export type Point = { x: number; y: number };
export type Layout = {
  positions: Record<string, Point>;
  notes: { id: string; text: string; position: Point }[];
  viewport?: Point & { zoom: number };
};
export type Workspace = {
  spec: Spec | null;
  plan: Plan;
  source: Source | null;
  edited: boolean;
  orchestrated: boolean;
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
  const point = (value?: Point) => Number.isFinite(value?.x) && Number.isFinite(value?.y);
  function usable(workspace: Workspace) {
    const layout = workspace?.layout;
    return workspace && isWorkspaceDraft(workspace.spec, workspace.plan)
      && (workspace.source === null || workspace.source === 'MANUAL' || workspace.source === 'IMPORTED' || workspace.source === 'PRESET')
      && typeof workspace.edited === 'boolean' && typeof workspace.orchestrated === 'boolean'
      && layout?.positions && typeof layout.positions === 'object' && !Array.isArray(layout.positions)
      && Object.values(layout.positions).every(point)
      && Array.isArray(layout.notes)
      && layout.notes.every((note) => typeof note?.id === 'string' && typeof note.text === 'string' && point(note.position))
      && (layout.viewport === undefined || (point(layout.viewport) && Number.isFinite(layout.viewport.zoom) && layout.viewport.zoom > 0));
  }
  if (!Array.isArray(data) || !data.every((item) => typeof item?.id === 'string' && typeof item?.name === 'string'
    && usable(item.workspace) && Array.isArray(item.history) && item.history.every((entry: Snapshot) => typeof entry?.id === 'string' && Number.isFinite(Date.parse(entry.at)) && usable(entry.workspace)))) {
    throw new Error('浏览器存储格式无法读取');
  }
  return data;
}

export function writeProjects(storage: Pick<Storage, 'setItem'>, projects: Project[]) {
  storage.setItem(key, JSON.stringify(projects));
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

export async function readJson(file: File): Promise<unknown> {
  if (file.size > 1024 * 1024) throw new Error('JSON 文件不得超过 1 MiB');
  try {
    return JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
  } catch {
    throw new Error('无法读取 JSON，请检查文件格式');
  }
}

export function downloadJson(filename: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
