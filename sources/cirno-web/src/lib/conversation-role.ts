/** Role capabilities are independent of the shared chat rendering and stream. */
export abstract class ConversationRole {
  abstract readonly name: "router" | "worker";
  abstract readonly canFork: boolean;
  abstract readonly inConversations: boolean;
  abstract readonly toolReplies: boolean;
}
export class RouterConversation extends ConversationRole {
  readonly name = "router";
  readonly canFork = false;
  readonly inConversations = false;
  readonly toolReplies = true;
}
export class WorkerConversation extends ConversationRole {
  readonly name = "worker";
  readonly canFork = true;
  readonly inConversations = true;
  readonly toolReplies = false;
}
const router = new RouterConversation(), worker = new WorkerConversation();
export const ROUTER_CHAT_ID = "b1ec9323-2155-5f24-bc56-1da2f59aeecb";
export const ROUTER_SESSION_KEY = `websocket:${ROUTER_CHAT_ID}`;
export function conversationRole(key: string | null | undefined): ConversationRole {
  return key === ROUTER_SESSION_KEY ? router : worker;
}

export function routerLabel(sessions: readonly import("./contracts/conversations").ChatSummary[]): string {
  const session = sessions.find(item => item.key === ROUTER_SESSION_KEY);
  return session?.handle?.name ? `@${session.handle.name}` : session?.title?.startsWith("@") ? session.title : "@cirno";
}
