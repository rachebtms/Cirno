import type { GoalStateWsPayload } from "@/lib/contracts/activity";
export function goalStateStripPreview(
  goal: GoalStateWsPayload | undefined,
  t: (key: string) => string,
): string | null {
  if (
    !goal ||
    (!goal.active &&
      !["paused", "waiting", "stopped", "blocked"].includes(goal.status ?? ""))
  )
    return null;
  const summary = goal.ui_summary?.trim();
  const objective = goal.objective?.trim();
  const label =
    summary ||
    (objective
      ? objective.length > 72
        ? `${objective.slice(0, 72)}…`
        : objective
      : t("thread.composer.goalStateFallback"));
  return goal.active
    ? label
    : `${t(`thread.composer.goalStatus.${goal.status}`)} · ${label}`;
}

export function buildGoalMarkdownBody(
  summary: string,
  objective: string,
): string {
  const s = summary.trim();
  const o = objective.trim();
  if (s && o) return `${s}\n\n---\n\n${o}`;
  return o || s;
}
