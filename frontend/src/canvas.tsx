import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow,
  ReactFlowProvider, useReactFlow, type Edge, type NodeChange, type NodeProps, type Viewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { linkError, type Plan } from './plan';
import { arrangeNodes, exportCanvas, noteSize, taskSize, type CanvasNode, type TaskNode, type NoteNode } from './canvas-tools';
import type { Layout, Point } from './storage';

function TaskCard({ data }: NodeProps<TaskNode>) {
  return <div className="task-card" data-tone={data.batch === undefined ? undefined : data.batch % 4}>
    <Handle type="target" position={Position.Left} aria-label="任务输入" />
    <strong>{data.title || '未命名任务'}</strong>
    <div className="node-meta">
      {[data.stage, data.role].filter(Boolean).length > 0 && <span>{[data.stage, data.role].filter(Boolean).join(' · ')}</span>}
      {data.priority && <span className="node-priority">{data.priority}</span>}
    </div>
    <Handle type="source" position={Position.Right} aria-label="任务输出" />
  </div>;
}

const NoteEditor = createContext<{
  editable: boolean;
  select(id: string): void;
  edit(id: string, text: string): void;
  remove(id: string): void;
} | null>(null);

function NoteCard({ id, data, selected }: NodeProps<NoteNode>) {
  const editor = useContext(NoteEditor);
  return <div className="note-card">
    <div className="note-heading">
      <strong>注释</strong>
      {editor?.editable && <button type="button" className="note-remove nodrag nopan"
        aria-label="删除注释" title="删除注释" onClick={(event) => { event.stopPropagation(); editor.remove(id); }}>×</button>}
    </div>
    <textarea className="note-input nodrag nopan nowheel" aria-label="注释内容"
      placeholder="点击编辑注释" rows={2} maxLength={500} readOnly={!editor?.editable} value={data.text}
      onFocus={() => { if (!selected) editor?.select(id); }}
      onChange={(event) => editor?.edit(id, event.target.value)} />
  </div>;
}

const nodeTypes = { task: TaskCard, note: NoteCard };

type Props = {
  plan: Plan; layout: Layout; selected: string | null; readonly: boolean; theme: 'light' | 'dark';
  batches?: string[][]; locateRequest: { id: string } | null;
  select(id: string | null): void; setLayout(apply: (current: Layout) => Layout): void; addTask(): void;
  connect(source: string, target: string): void; notice(message: string): void;
};

function Graph({ plan, layout, selected, readonly, theme, batches, locateRequest, select, setLayout, addTask, connect, notice }: Props) {
  const [hand, setHand] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragPositions, setDragPositions] = useState<Map<string, Point>>(() => new Map());
  const [measurements, setMeasurements] = useState<Map<string, { width: number; height: number }>>(() => new Map());
  const initialViewport = useRef(layout.viewport);
  const noteTool = useRef<HTMLButtonElement>(null);
  const { fitView, getNodes, screenToFlowPosition } = useReactFlow<CanvasNode, Edge>();
  const ids = useMemo(() => new Set(plan.tasks.map((task) => task.task_id)), [plan]);
  const batchByTask = useMemo(() => new Map(batches?.flatMap((batch, index) => batch.map((id) => [id, index] as const))), [batches]);
  const layoutNodes = useMemo<CanvasNode[]>(() => [
    ...plan.tasks.map((task, index): TaskNode => ({
      id: task.task_id, type: 'task', ...taskSize, measured: measurements.get(task.task_id), data: { title: task.name, stage: task.stage, role: task.assigned_role,
        priority: { high: '高', medium: '中', low: '低' }[task.priority], batch: batchByTask.get(task.task_id) },
      position: Object.hasOwn(layout.positions, task.task_id) ? layout.positions[task.task_id]
        : { x: (index % 3) * 320, y: Math.floor(index / 3) * 140 },
      selected: selected === task.task_id, ariaLabel: task.name || '未命名任务',
    })),
    ...layout.notes.map((note): NoteNode => ({ id: note.id, type: 'note', position: note.position,
      ...noteSize, dragHandle: '.note-heading', data: { text: note.text }, selected: selected === note.id, ariaLabel: '注释' })),
  ], [plan, layout.positions, layout.notes, selected, batchByTask, measurements]);
  const nodes = useMemo(() => layoutNodes.map((node) => {
    const position = dragPositions.get(node.id);
    return position ? { ...node, position, dragging: true } : node;
  }), [layoutNodes, dragPositions]);
  const edges = useMemo<Edge[]>(() => plan.tasks.flatMap((task) => [...new Set(task.dependencies)]
    .filter((source) => ids.has(source) && source !== task.task_id)
    .map((source) => ({
      id: JSON.stringify([source, task.task_id]), source, target: task.task_id,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b' }, style: { stroke: '#64748b', strokeWidth: 1.5 },
    }))), [plan, ids]);

  useEffect(() => {
    if (!locateRequest) return;
    const frame = requestAnimationFrame(() => {
      void fitView({ nodes: [locateRequest], padding: 0.35, maxZoom: 1.1 });
    });
    return () => cancelAnimationFrame(frame);
  }, [fitView, locateRequest]);

  function arrange() {
    try {
      const tasks = arrangeNodes(plan, getNodes()).filter((node) => node.type === 'task');
      if (!tasks.length) return;
      setLayout((current) => ({
        ...current,
        positions: Object.fromEntries(tasks.map(({ id, position }) => [id, position])),
      }));
      requestAnimationFrame(() => void fitView({ nodes: tasks, padding: 0.2, maxZoom: 1 }));
    } catch (error) {
      notice(error instanceof Error ? error.message : '无法整理节点');
    }
  }

  async function png() {
    setBusy(true);
    try {
      await exportCanvas(getNodes(), edges);
      notice('已导出画布 PNG');
    } catch (error) {
      notice(error instanceof Error ? error.message : '无法导出画布 PNG');
    } finally {
      setBusy(false);
    }
  }

  function storeViewport(_: unknown, viewport: Viewport) {
    if (readonly || (layout.viewport?.x === viewport.x && layout.viewport.y === viewport.y && layout.viewport.zoom === viewport.zoom)) return;
    setLayout((current) => ({ ...current, viewport }));
  }

  function updateNodes(changes: NodeChange<CanvasNode>[]) {
    const measuredTasks = changes.flatMap((change) => change.type === 'dimensions' && change.dimensions && ids.has(change.id)
      ? [[change.id, change.dimensions] as const] : []);
    if (measuredTasks.length) {
      // Keep React Flow's measured handle bounds when the controlled task node changes position.
      setMeasurements((current) => {
        let next = current;
        for (const [id, size] of measuredTasks) {
          const previous = current.get(id);
          if (previous?.width === size.width && previous.height === size.height) continue;
          if (next === current) next = new Map(current);
          next.set(id, size);
        }
        return next;
      });
    }
    const selection = changes.flatMap((change) => change.type === 'select' && change.selected ? [change.id] : []);
    if (!hand && !placing && selection.length === 1 && selection[0] !== selected) select(selection[0]);
    if (readonly) return;
    const moving = new Map<string, Point>();
    const committed = new Map<string, Point>();
    for (const change of changes) {
      if (change.type !== 'position' || !change.position) continue;
      (change.dragging ? moving : committed).set(change.id, change.position);
    }
    if (!moving.size && !committed.size) return;

    // Keep pointer movement local to the canvas and commit positions when the drag ends.
    setDragPositions((current) => {
      if (!moving.size && ![...committed.keys()].some((id) => current.has(id))) return current;
      const next = new Map(current);
      for (const [id, point] of moving) next.set(id, point);
      for (const id of committed.keys()) next.delete(id);
      return next;
    });
    if (committed.size) {
      setLayout((current) => ({
        ...current,
        positions: { ...current.positions, ...Object.fromEntries([...committed].filter(([id]) => ids.has(id))) },
        notes: current.notes.map((note) => {
          const position = committed.get(note.id);
          return position ? { ...note, position } : note;
        }),
      }));
    }
  }

  const noteEditor = useMemo(() => ({
    editable: !readonly && !hand && !placing,
    select,
    edit: (id: string, text: string) => setLayout((current) => ({
      ...current, notes: current.notes.map((note) => note.id === id ? { ...note, text } : note),
    })),
    remove: (id: string) => {
      setLayout((current) => ({ ...current, notes: current.notes.filter((note) => note.id !== id) }));
      select(null);
      noteTool.current?.focus();
    },
  }), [readonly, hand, placing, select, setLayout]);

  return <section className="graph" aria-label="工作流画布">
    <div className="canvas-toolbar" role="group" aria-label="画布工具">
      {!readonly && <>
        <button aria-label="添加任务" title="添加任务" onClick={addTask}>+</button>
        <button ref={noteTool} aria-label="添加注释" title="添加注释" aria-pressed={placing} onClick={() => { setPlacing(!placing); setHand(false); }}>▤</button>
        <button aria-label="选择" title="选择" aria-pressed={!hand && !placing} onClick={() => { setHand(false); setPlacing(false); }}>↖</button>
        <button aria-label="平移" title="平移" aria-pressed={hand} onClick={() => { setHand(true); setPlacing(false); }}>✋︎</button>
        <button aria-label="自动布局" title="自动布局" onClick={arrange} disabled={!plan.tasks.length}>▦</button>
      </>}
      <button aria-label="导出 PNG" title="导出 PNG" onClick={() => void png()} disabled={!nodes.length || busy}>⇩</button>
    </div>
    {placing && <p className="placement-tip" role="status">点击画布放置注释</p>}
    <div className={'flow' + (placing ? ' placing' : hand ? ' hand' : '')}>
      <NoteEditor.Provider value={noteEditor}>
        <ReactFlow<CanvasNode, Edge> nodes={nodes} edges={edges} nodeTypes={nodeTypes} colorMode={theme}
          defaultViewport={initialViewport.current} fitView={!initialViewport.current} fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
          deleteKeyCode={null} minZoom={0.25} maxZoom={2} panActivationKeyCode="Space"
          nodesDraggable={!readonly && !hand && !placing} nodesConnectable={!readonly && !hand && !placing}
          elementsSelectable={!hand && !placing} selectionOnDrag={!readonly && !hand && !placing} selectNodesOnDrag={false}
          panOnDrag={hand || readonly ? true : [1, 2]} onMoveEnd={storeViewport}
          onNodesChange={updateNodes}
          onNodeClick={(_, node) => { if (!hand && !placing) select(node.id); }}
          onPaneClick={(event) => {
            if (placing && !readonly) {
              const id = 'note_' + crypto.randomUUID();
              setLayout((current) => ({ ...current, notes: [...current.notes, { id, text: '', position: screenToFlowPosition({ x: event.clientX, y: event.clientY }) }] }));
              setPlacing(false);
              select(id);
            } else select(null);
          }}
          isValidConnection={({ source, target }) => !linkError(plan, source, target)}
          onConnect={({ source, target }) => connect(source, target)}
          onConnectEnd={(_, state) => {
            if (!state.isValid && state.fromHandle && state.toHandle) {
              const [source, target] = state.fromHandle.type === 'source'
                ? [state.fromHandle, state.toHandle] : [state.toHandle, state.fromHandle];
              notice(linkError(plan, source.nodeId, target.nodeId) ?? '请连接上游输出与下游输入');
            }
          }}>
          <Background gap={20} size={1} color={theme === 'dark' ? '#33435b' : '#b7c4d4'} />
          <Controls showInteractive={false} />
          {nodes.length > 0 && <MiniMap pannable zoomable style={{ width: 124, height: 78 }} nodeColor={theme === 'dark' ? '#7992ba' : '#8ba8ca'} maskColor={theme === 'dark' ? 'rgba(9,17,31,.58)' : 'rgba(221,228,239,.62)'} />}
        </ReactFlow>
      </NoteEditor.Provider>
      {!nodes.length && !placing && <div className="canvas-empty">{readonly ? '暂无工作流' : <button onClick={addTask}>＋ 创建首个任务</button>}</div>}
    </div>
  </section>;
}

export function WorkflowCanvas(props: Props) {
  return <ReactFlowProvider><Graph {...props} /></ReactFlowProvider>;
}
