export function selectionRange(
  order: string[],
  anchorKey: string,
  targetKey: string,
): string[] | null {
  const anchorIndex = order.indexOf(anchorKey);
  const targetIndex = order.indexOf(targetKey);
  if (anchorIndex < 0 || targetIndex < 0) return null;
  const start = Math.min(anchorIndex, targetIndex);
  const end = Math.max(anchorIndex, targetIndex);
  return order.slice(start, end + 1);
}
