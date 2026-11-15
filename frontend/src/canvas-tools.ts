import type { Edge, Node, XYPosition } from '@xyflow/react';
import type { Plan } from './plan';

export type TaskNode = Node<{ title: string; stage: string; role: string; priority: string; batch?: number }, 'task'>;
export type NoteNode = Node<{ text: string }, 'note'>;
export const taskSize = { width: 240, height: 96 };
export const noteSize = { width: 240, height: 108 };
export type CanvasNode = TaskNode | NoteNode;

export function arrangeNodes(plan: Plan, nodes: CanvasNode[]): CanvasNode[] {
  const depths = new Map<string, number>();
  const remaining = new Set(plan.tasks);
  while (remaining.size) {
    const ready = [...remaining].filter((task) => task.dependencies.every((id) => depths.has(id)));
    if (!ready.length) throw new Error('计划包含无效依赖，无法整理节点。');
    for (const task of ready) {
      depths.set(task.task_id, Math.max(0, ...task.dependencies.map((id) => depths.get(id)! + 1)));
      remaining.delete(task);
    }
  }
  const positions = new Map<string, XYPosition>();
  const heights = new Map<number, number>();
  for (const node of nodes) {
    if (node.type === 'note') continue;
    const depth = depths.get(node.id) ?? 0;
    const y = heights.get(depth) ?? 0;
    positions.set(node.id, { x: depth * 320, y });
    heights.set(depth, y + (node.height ?? node.measured?.height ?? taskSize.height) + 40);
  }
  return nodes.map((node) => {
    const position = positions.get(node.id);
    return position ? { ...node, position } : node;
  });
}

export async function exportCanvas(nodes: CanvasNode[], edges: Edge[]) {
  if (!nodes.length) throw new Error('画布为空。');
  await document.fonts.ready;
  const boxes = nodes.map((node) => ({ ...node.position, node,
    width: node.width ?? node.measured?.width ?? (node.type === 'note' ? noteSize.width : taskSize.width),
    height: node.height ?? node.measured?.height ?? (node.type === 'note' ? noteSize.height : taskSize.height),
  }));
  const left = Math.min(...boxes.map(({ x }) => x)) - 32;
  const top = Math.min(...boxes.map(({ y }) => y)) - 32;
  const width = Math.max(...boxes.map((box) => box.x + box.width)) - left + 32;
  const height = Math.max(...boxes.map((box) => box.y + box.height)) - top + 32;
  const scale = Math.min(2, 8192 / Math.max(width, height), Math.sqrt(16_000_000 / width / height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.ceil(width * scale));
  canvas.height = Math.max(1, Math.ceil(height * scale));
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('当前浏览器无法导出图片。');
  ctx.scale(scale, scale);
  ctx.fillStyle = '#eff2f7';
  ctx.fillRect(0, 0, width, height);
  ctx.translate(-left, -top);
  const byId = new Map(boxes.map((box) => [box.node.id, box]));
  for (const edge of edges) {
    const source = byId.get(edge.source), target = byId.get(edge.target);
    if (!source || !target) continue;
    const x = source.x + source.width, y = source.y + source.height / 2;
    const toX = target.x, toY = target.y + target.height / 2;
    const bend = Math.max(32, Math.abs(toX - x) / 2);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.bezierCurveTo(x + bend, y, toX - bend, toY, toX, toY);
    ctx.strokeStyle = '#7386a8';
    ctx.lineWidth = 1.6;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(toX, toY);
    ctx.lineTo(toX - 8, toY - 4);
    ctx.lineTo(toX - 8, toY + 4);
    ctx.fillStyle = '#7386a8';
    ctx.fill();
  }
  for (const { node, x, y, width, height } of boxes) {
    const note = node.type === 'note';
    ctx.beginPath();
    ctx.roundRect(x, y, width, height, 10);
    ctx.fillStyle = note ? '#fff8df' : '#ffffff';
    ctx.fill();
    ctx.strokeStyle = note ? '#ead58b' : '#ccd5e4';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.save();
    ctx.clip();
    ctx.fillStyle = note ? '#715416' : '#17243b';
    ctx.font = `${note ? 400 : 600} 14px "Segoe UI", "Microsoft YaHei", sans-serif`;
    ctx.textBaseline = 'top';
    const text = note ? node.data.text || '注释' : node.data.title;
    let line = '', row = y + 12;
    for (const char of text) {
      if (char === '\n' || ctx.measureText(line + char).width > width - 24) {
        ctx.fillText(line, x + 12, row);
        row += 20;
        line = '';
      }
      if (char !== '\n') line += char;
    }
    ctx.fillText(line, x + 12, row);
    ctx.restore();
  }
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('无法生成 PNG 图片。');
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'flowstudio-canvas.png';
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
