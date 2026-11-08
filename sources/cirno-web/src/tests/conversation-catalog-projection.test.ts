import { projectConversationCatalog } from "@/features/conversations/catalog/projection";
import type { ConversationCatalog } from "@/features/conversations/catalog/context";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { describe, expect, it } from "vitest";

function row(key: string, title: string, projectId?: string): ChatSummary {
  return { key, title, projectId, preview: "", chatId: key, channel: "websocket", createdAt: null, updatedAt: null };
}
const input: Pick<ConversationCatalog, "sessions" | "projects" | "preferences" | "showArchived"> = {
  sessions: [row("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "Cirno"), row("a", "Zebra", "p"), row("b", "Apple", "p"), row("c", "Hidden", "p"), row("d", "Old project", "removed")],
  projects: [{ id: "p", name: "Spectroscopy" }], showArchived: false,
  preferences: { pinned_keys: ["a"], archived_keys: ["c"], title_overrides: { b: "Corrected name" },
    view: { sort: "title_asc", density: "comfortable", show_archived: false } },
};

describe("conversation catalog projection", () => {
  it("uses shared ordering, includes project matches and excludes Cirno and hidden archives", () => {
    const result = projectConversationCatalog(input, "Spectroscopy");
    expect(result.groups[0].members.map(row => row.key)).toEqual(["a", "b"]);
    expect(result.unfiled).toEqual([]);
    expect(projectConversationCatalog(input, "Corrected name").groups[0].members.map(row => row.key)).toEqual(["b"]);
    expect(projectConversationCatalog(input, "Apple").groups).toEqual([]);
    expect(projectConversationCatalog(input, "Cirno").unfiled).toEqual([]);
  });
  it("keeps missing-project conversations accessible and reveals archived records when requested", () => {
    const result = projectConversationCatalog({ ...input, showArchived: true }, "");
    expect(result.groups[0].members.map(row => row.key)).toEqual(["a", "b", "c"]);
    expect(result.unfiled.map(row => row.key)).toEqual(["d"]);
  });
});
