export function conversationActivityState(
  chatId: string,
  active: boolean,
  states: {
    running: ReadonlySet<string>;
    recovery: ReadonlySet<string>;
    updated: ReadonlySet<string>;
  },
): "running" | "recovery" | "updated" | null {
  if (states.running.has(chatId)) return "running";
  if (states.recovery.has(chatId)) return "recovery";
  return states.updated.has(chatId) && !active ? "updated" : null;
}
