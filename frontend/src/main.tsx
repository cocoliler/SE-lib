import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow,
  ReactFlowProvider, useNodesState, useReactFlow, type Edge, type Node, type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { canLink, examplePlan, type Plan, type Task } from './plan';
import './style.css';

type TaskNode = Node<{ title: string; index: number }, 'task'>;
const STORAGE = 'flowstudio-t04-draft';

function TaskCard({ data, selected }: NodeProps<TaskNode>) {
  return <div className={selected ? 'task-card selected' : 'task-card'}>
    <Handle type="target" position={Position.Left} aria-label="任务输入" />
    <div className="task-top">
      <span className="task-icon" aria-hidden="true">{data.index === 1 ? '▤' : '◇'}</span>
      <span className="task-number">任务 {String(data.index).padStart(2, '0')}</span>
    </div>
    <strong>{data.title}</strong>
    <span className="task-state"><i />待执行</span>
    <Handle type="source" position={Position.Right} aria-label="任务输出" />
  </div>;
}

const nodeTypes = { task: TaskCard };
const initialPosition = (index: number) => ({
  x: (index % 2) * 330, y: Math.floor(index / 2) * 190,
});

function makeNode(task: Task, index: number): TaskNode {
  return { id: task.id, type: 'task', data: { title: task.title, index: index + 1 },
    position: initialPosition(index), ariaLabel: task.title };
}

function loadDraft(): { plan: Plan; layout: Record<string, TaskNode['position']> } {
  try {
    const raw = localStorage.getItem(STORAGE);
    if (raw) {
      const draft = JSON.parse(raw);
      if (Array.isArray(draft?.plan?.tasks) && draft.plan.tasks.length && draft.layout) {
        const tasks: Task[] = draft.plan.tasks;
        const ids = new Set(tasks.map((task) => task.id));
        if (ids.size === tasks.length && tasks.every((task) =>
          typeof task.id === 'string' && typeof task.title === 'string' &&
          Array.isArray(task.depends_on) && task.depends_on.every((id) => ids.has(id)))) {
          return draft;
        }
      }
    }
  } catch {
    // Show the example if storage is unavailable or contains an unreadable draft.
  }
  return { plan: examplePlan, layout: {} };
}

function Editor() {
  const [draft] = useState(loadDraft);
  const [plan, setPlan] = useState(draft.plan);
  const [nodes, setNodes, onNodesChange] = useNodesState<TaskNode>(
    draft.plan.tasks.map((task, index) => {
      const node = makeNode(task, index);
      const point = draft.layout[task.id];
      return Number.isFinite(point?.x) && Number.isFinite(point?.y) ? { ...node, position: point } : node;
    }),
  );
  const [selectedId, setSelectedId] = useState<string | null>(draft.plan.tasks[0].id);
  const [notice, setNotice] = useState('');
  const [dirty, setDirty] = useState(false);
  const { fitView } = useReactFlow<TaskNode, Edge>();
  const selected = plan.tasks.find((task) => task.id === selectedId);
  const edges: Edge[] = plan.tasks.flatMap((task) => task.depends_on.map((source) => ({
    id: JSON.stringify([source, task.id]), source, target: task.id,
    type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: '#5971a5' },
    style: { stroke: '#5971a5', strokeWidth: 2 },
  })));

  function select(id: string | null) {
    setSelectedId(id);
    setNodes((current) => current.map((node) => ({ ...node, selected: node.id === id })));
  }

  function save() {
    try {
      localStorage.setItem(STORAGE, JSON.stringify({
        plan, layout: Object.fromEntries(nodes.map(({ id, position }) => [id, position])),
      }));
      setDirty(false);
      setNotice('已保存到此浏览器。');
    } catch {
      setNotice('无法保存，请检查浏览器存储权限。');
    }
  }

  function addTask() {
    const task = { id: `task_${crypto.randomUUID().replaceAll('-', '').slice(0, 16)}`,
      title: '新任务', depends_on: [] };
    setPlan((current) => ({ tasks: [...current.tasks, task] }));
    setNodes((current) => [...current.map((node) => ({ ...node, selected: false })),
      { ...makeNode(task, current.length), selected: true }]);
    setSelectedId(task.id);
    setDirty(true);
    requestAnimationFrame(() => void fitView({ padding: 0.24, duration: 200, maxZoom: 1 }));
  }

  function rename(title: string) {
    if (!selected) return;
    setPlan((current) => ({ tasks: current.tasks.map((task) => task.id === selected.id ? { ...task, title } : task) }));
    setNodes((current) => current.map((node) => node.id === selected.id
      ? { ...node, data: { ...node.data, title }, ariaLabel: title } : node));
    setDirty(true);
  }

  return <div className="workspace">
    <header className="topbar">
      <div className="brand"><span className="brand-mark" aria-hidden="true">↳</span>FlowStudio</div>
      <span className="breadcrumb">工作台 / 编排画布</span>
      <div className="top-actions">
        <span className="test-label">TEST · 示例计划</span>
        <button className="primary" onClick={save}>保存草稿</button>
      </div>
    </header>
    <main>
      <section className="project">
        <div><h1>缺陷跟踪工具</h1><p>整理项目需求，设计缺陷状态流转与测试方案。</p></div>
        <span className="draft-state"><i />{dirty ? '有未保存的修改' : '本地草稿'}</span>
      </section>
      <div className="editor">
        <aside className="tasks" aria-label="任务列表">
          <div className="panel-heading"><h2>任务列表</h2><span>{plan.tasks.length}</span></div>
          <div className="task-list">{plan.tasks.map((task, index) =>
            <button key={task.id} className={task.id === selectedId ? 'list-task active' : 'list-task'}
              aria-pressed={task.id === selectedId} onClick={() => select(task.id)}>
              <span className="list-number">{String(index + 1).padStart(2, '0')}</span>{task.title || '未命名任务'}
            </button>)}</div>
          <button className="add" onClick={addTask}>＋ 新建任务</button>
        </aside>
        <section className="graph" aria-label="任务依赖画布">
          <div className="graph-bar"><h2>任务依赖</h2><span><i />{edges.length} 条依赖</span></div>
          <div className="flow">
            <ReactFlow<TaskNode, Edge> nodes={nodes} edges={edges} nodeTypes={nodeTypes}
              fitView fitViewOptions={{ padding: 0.24, maxZoom: 1 }} minZoom={0.15} maxZoom={1.8}
              deleteKeyCode={null}
              onNodesChange={onNodesChange} onNodeDragStop={() => setDirty(true)}
              onNodeClick={(_, node) => select(node.id)} onPaneClick={() => select(null)}
              onSelectionChange={({ nodes: selection }) => {
                if (selection.length === 1) setSelectedId(selection[0].id);
              }}
              isValidConnection={({ source, target }) => canLink(plan, source, target)}
              onConnect={({ source, target }) => {
                if (!canLink(plan, source, target)) return;
                setPlan((current) => ({ tasks: current.tasks.map((task) => task.id === target
                  ? { ...task, depends_on: [...task.depends_on, source] } : task) }));
                setDirty(true);
              }}>
              <Background gap={22} size={1.2} color="#b5c5e2" />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable nodeColor="#7a9bef" maskColor="rgba(230,238,253,.65)" />
            </ReactFlow>
          </div>
        </section>
        <aside className="details" aria-label="任务详情">
          <div className="panel-heading"><h2>任务详情</h2></div>
          {selected ? <div className="detail-body">
            <label htmlFor="title">任务名称</label>
            <input id="title" maxLength={200} value={selected.title}
              onChange={(event) => rename(event.target.value)}
              onBlur={() => { if (!selected.title.trim()) rename('未命名任务'); }} />
            <dl><dt>任务 ID</dt><dd><code>{selected.id}</code></dd><dt>执行状态</dt><dd className="task-state"><i />待执行</dd></dl>
            <h3>上游依赖</h3>
            {selected.depends_on.length ? <ul>{selected.depends_on.map((id) => <li key={id}>
              <button className="text-button" onClick={() => select(id)}>{plan.tasks.find((task) => task.id === id)?.title || id}</button>
              <button className="unlink" aria-label={`移除依赖 ${id}`} title="移除依赖" onClick={() => {
                setPlan((current) => ({ tasks: current.tasks.map((task) => task.id === selected.id
                  ? { ...task, depends_on: task.depends_on.filter((dep) => dep !== id) } : task) }));
                setDirty(true);
              }}>×</button>
            </li>)}</ul> : <p className="muted">无上游依赖</p>}
          </div> : <p className="detail-body muted">选择一个任务查看详情。</p>}
        </aside>
      </div>
      <footer><span>从上游节点右侧连接到下游节点左侧。</span><span role="status">{notice}</span></footer>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<ReactFlowProvider><Editor /></ReactFlowProvider>);
