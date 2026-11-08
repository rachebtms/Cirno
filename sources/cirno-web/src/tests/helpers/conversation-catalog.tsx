import { ConversationCatalogContext, type ConversationCatalog } from "@/features/conversations/catalog/context";
import { ConversationsPage } from "@/features/conversations/ConversationsPage";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { render } from "@testing-library/react";
import { vi } from "vitest";

export function catalogFixture(overrides: Partial<ConversationCatalog> = {}): ConversationCatalog {
  return {
    owner: {},
    sessions: [
      conversation("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "Cirno"),
      conversation("websocket:worker", "Review paper", "research"),
      conversation("websocket:other", "Investigate data"),
    ],
    showArchived: false, toggleArchived: vi.fn(), rename: vi.fn(async () => undefined),
    togglePin: vi.fn(), toggleArchive: vi.fn(), deleteConversation: vi.fn(),
    deleteMany: vi.fn(), archiveMany: vi.fn(), setSort: vi.fn(),
    projects: [{ id: "research", name: "Research" }],
    loading: false,
    open: vi.fn(),
    create: vi.fn(),
    saveProject: vi.fn(async () => undefined),
    deleteProject: vi.fn(async () => undefined),
    assign: vi.fn(),
    ...overrides,
  };
}

export function conversation(
  key: string,
  title: string,
  projectId?: string,
): ChatSummary {
  return {
    key,
    title,
    projectId,
    channel: "websocket",
    chatId: key.split(":")[1],
    preview: "Saved research",
    createdAt: null,
    updatedAt: null,
  };
}
export function renderCatalog(overrides: Partial<ConversationCatalog> = {}) {
  const catalog = catalogFixture(overrides);
  render(
    <ConversationCatalogContext.Provider value={catalog}>
      <ConversationsPage />
    </ConversationCatalogContext.Provider>,
  );
  return catalog;
}
