import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow,
  ReactFlowProvider, useNodesState, useReactFlow, type Edge, type Node, type NodeProps,
  type OnConnectEnd, type OnConnectStartParams,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { linkError, examplePlan, type Plan, type Task } from './plan';
import './style.css';

type TaskNode = Node<{ title: string; index: number }, 'task'>;
const STORAGE = 'flowstudio-t04-draft';
const GOAL_LIMIT = 4000;
const EXAMPLE_GOAL = '设计团队缺陷跟踪工具，支持项目、负责人和状态流转，并给出测试方案。';

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

function loadDraft(): { plan: Plan; layout: Record<string, TaskNode['position']>; goal: string } {
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
          const goal = typeof draft.goal === 'string' ? draft.goal.slice(0, GOAL_LIMIT) : '';
          return { plan: draft.plan, layout: draft.layout, goal };
        }
      }
    }
  } catch {
    // Show the example if storage is unavailable or contains an unreadable draft.
  }
  return { plan: examplePlan, layout: {}, goal: '' };
}

function Editor() {
  const [draft] = useState(loadDraft);
  const [plan, setPlan] = useState(draft.plan);
  const [goal, setGoal] = useState(draft.goal);
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
  const clickStart = useRef<OnConnectStartParams | null>(null);
  useEffect(() => {
    if (!dirty) return;
    function confirmLeaving(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = true;
    }
    window.addEventListener('beforeunload', confirmLeaving);
    return () => window.removeEventListener('beforeunload', confirmLeaving);
  }, [dirty]);
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

  function markChanged() {
    setDirty(true);
    setNotice('');
  }

  function explainLink(sourceId: string, sourceType: string, targetId: string, targetType: string) {
    if (sourceType === targetType) {
      setNotice('请连接上游任务的输出端和下游任务的输入端。');
      return;
    }
    const [source, target] = sourceType === 'source' ? [sourceId, targetId] : [targetId, sourceId];
    const error = linkError(plan, source, target);
    if (error) setNotice(error);
  }

  const showConnectionError: OnConnectEnd = (_, { fromHandle, toHandle, isValid }) => {
    if (!isValid && fromHandle && toHandle) {
      explainLink(fromHandle.nodeId, fromHandle.type, toHandle.nodeId, toHandle.type);
    }
  };

  function save() {
    try {
      localStorage.setItem(STORAGE, JSON.stringify({
        goal, plan, layout: Object.fromEntries(nodes.map(({ id, position }) => [id, position])),
      }));
      setDirty(false);
      setNotice('已保存到此浏览器。');
    } catch {
      setNotice('无法保存，请检查浏览器存储权限。');
    }
  }

  function editGoal(value: string) {
    if (value === goal) return;
    setGoal(value);
    markChanged();
  }

  function loadExample() {
    if (!goal.trim()) return;
    const hasCanvasChanges = JSON.stringify(plan) !== JSON.stringify(examplePlan)
      || nodes.some(({ position }, index) => {
        const initial = initialPosition(index);
        return position.x !== initial.x || position.y !== initial.y;
      });
    if (hasCanvasChanges) {
      if (!window.confirm('加载示例将替换当前画布的任务、连线和位置。你填写的需求会保留。继续吗？')) return;
      setPlan(examplePlan);
      setNodes(examplePlan.tasks.map((task, index) => ({
        ...makeNode(task, index), selected: index === 0,
      })));
      setSelectedId(examplePlan.tasks[0].id);
      markChanged();
      requestAnimationFrame(() => void fitView({ padding: 0.24, duration: 200, maxZoom: 1 }));
    }
    setNotice('当前画布已显示 TEST 示例计划。');
  }

  function addTask() {
    const task = { id: `task_${crypto.randomUUID().replaceAll('-', '').slice(0, 16)}`,
      title: '新任务', depends_on: [] };
    setPlan((current) => ({ tasks: [...current.tasks, task] }));
    setNodes((current) => [...current.map((node) => ({ ...node, selected: false })),
      { ...makeNode(task, current.length), selected: true }]);
    setSelectedId(task.id);
    markChanged();
    requestAnimationFrame(() => void fitView({ padding: 0.24, duration: 200, maxZoom: 1 }));
  }

  function rename(title: string) {
    if (!selected) return;
    setPlan((current) => ({ tasks: current.tasks.map((task) => task.id === selected.id ? { ...task, title } : task) }));
    setNodes((current) => current.map((node) => node.id === selected.id
      ? { ...node, data: { ...node.data, title }, ariaLabel: title } : node));
    markChanged();
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
        <h1>编排工作台</h1>
        <span className="draft-state"><i />{dirty ? '有未保存的修改' : '本地草稿'}</span>
      </section>
      <form className="goal-form" onSubmit={(event) => {
        event.preventDefault();
        loadExample();
      }}>
        <label htmlFor="goal">项目需求</label>
        <textarea id="goal" rows={1} maxLength={GOAL_LIMIT} value={goal}
          aria-description="加载时使用固定的 TEST 示例。需求可随草稿保存。"
          placeholder="描述项目目标与验收要求"
          onChange={(event) => editGoal(event.target.value)} />
        <div className="goal-actions">
          <button type="button" className="text-button" disabled={goal === EXAMPLE_GOAL} onClick={() => {
            if (goal.trim() && !window.confirm('用示例需求替换当前填写的内容？')) return;
            editGoal(EXAMPLE_GOAL);
          }}>填入示例</button>
          <button className="primary" type="submit" disabled={!goal.trim()}>加载示例计划</button>
        </div>
      </form>
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
              onNodesChange={(changes) => {
                onNodesChange(changes);
                if (changes.some((change) => change.type === 'position' && change.position)) markChanged();
              }}
              onNodeClick={(_, node) => select(node.id)} onPaneClick={() => select(null)}
              onSelectionChange={({ nodes: selection }) => {
                if (selection.length === 1) setSelectedId(selection[0].id);
              }}
              isValidConnection={({ source, target }) => linkError(plan, source, target) === null}
              onConnectStart={() => setNotice('')}
              onConnectEnd={showConnectionError}
              onClickConnectStart={(_, start) => {
                clickStart.current = start;
                setNotice('');
              }}
              onClickConnectEnd={(event) => {
                const start = clickStart.current;
                clickStart.current = null;
                // Click connections do not always include the hovered handle in React Flow's state.
                const end = event.target instanceof Element
                  ? event.target.closest<HTMLElement>('.react-flow__handle') : null;
                const endId = end?.dataset.nodeid;
                if (start?.nodeId && start.handleType && endId && end) {
                  explainLink(start.nodeId, start.handleType, endId,
                    end.classList.contains('source') ? 'source' : 'target');
                }
              }}
              onConnect={({ source, target }) => {
                if (linkError(plan, source, target)) return;
                setPlan((current) => ({ tasks: current.tasks.map((task) => task.id === target
                  ? { ...task, depends_on: [...task.depends_on, source] } : task) }));
                markChanged();
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
                markChanged();
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
