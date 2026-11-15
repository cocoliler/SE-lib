import type { CanvasNote, LayoutWriteRequest, Position } from './api/generated/contracts';

export type Point = Position;
type LocalNote = Omit<CanvasNote, 'x' | 'y'> & { position: Point };
export type Layout = Omit<LayoutWriteRequest, 'expected_revision' | 'notes' | 'viewport'> & {
  notes: LocalNote[];
  viewport?: LayoutWriteRequest['viewport'];
};
export type StoredLayout = Omit<Layout, 'notes'> & { notes: CanvasNote[] };

export function encodeLayout(layout: Layout): StoredLayout {
  return {
    ...layout,
    notes: layout.notes.map(({ position: { x, y }, ...note }) => ({ ...note, x, y })),
  };
}

export function decodeLayout(layout: Layout | StoredLayout | undefined): Layout | undefined {
  const isPoint = (value?: Point) => Number.isFinite(value?.x) && Number.isFinite(value?.y);
  if (!layout?.positions || typeof layout.positions !== 'object' || Array.isArray(layout.positions)
    || !Object.values(layout.positions).every(isPoint) || !Array.isArray(layout.notes)) return;
  const viewport = layout.viewport;
  if (viewport !== undefined && (!isPoint(viewport) || !Number.isFinite(viewport.zoom) || viewport.zoom <= 0)) return;

  const notes: LocalNote[] = [];
  for (const note of layout.notes) {
    if (!note || typeof note.id !== 'string' || typeof note.text !== 'string') return;
    const position = 'position' in note ? note.position : { x: note.x, y: note.y };
    if (!isPoint(position)) return;
    const { id, text, color } = note;
    notes.push({ id, text, ...(color === undefined ? {} : { color }), position });
  }
  return { positions: layout.positions, notes, ...(viewport ? { viewport } : {}) };
}
