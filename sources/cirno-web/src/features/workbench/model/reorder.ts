export function reorderItems<T extends { id: string }>(items: T[], id: string, target: string): T[] {
  const from = items.findIndex(item => item.id === id);
  const to = items.findIndex(item => item.id === target);
  if (from < 0 || to < 0 || from === to) return items;
  const next = [...items];
  next.splice(to, 0, ...next.splice(from, 1));
  return next;
}
