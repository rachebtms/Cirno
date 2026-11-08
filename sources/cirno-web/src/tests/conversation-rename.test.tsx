import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { catalogFixture } from "./helpers/conversation-catalog";
import { ConversationCatalogContext } from "@/features/conversations/catalog/context";
import { ConversationsPage } from "@/features/conversations/ConversationsPage";
import type { ChatSummary } from "@/lib/contracts/conversations";

const topic: ChatSummary = {
  key: "websocket:review", chatId: "review", channel: "websocket",
  title: "Review", preview: "", createdAt: null, updatedAt: null,
};

function RenameCase({
  save,
  grouped = false,
  onSelect = vi.fn(),
}: {
  save: (key: string, title: string) => Promise<void>;
  grouped?: boolean;
  onSelect?: (key: string) => void;
}) {
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [owner] = useState({});
  return <ConversationCatalogContext.Provider value={catalogFixture({
    owner,
    sessions: [{ ...topic, projectId: grouped ? "research" : undefined }, { ...topic, key: "websocket:other", chatId: "other", title: "Other" }],
    preferences: { pinned_keys: [], archived_keys: [], title_overrides: titles },
    open: onSelect,
    rename: async (key, nextTitle) => {
      await save(key, nextTitle);
      setTitles(current => ({ ...current, [key]: nextTitle }));
    },
  })}><ConversationsPage /></ConversationCatalogContext.Provider>;
}

async function startRename(user: ReturnType<typeof userEvent.setup>, title = "Review") {
  await user.click(screen.getByRole("button", { name: `Conversation actions for ${title}` }));
  await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
  return screen.findByRole("textbox", { name: /^Conversation name/ });
}

describe("conversation rename", () => {
  it.each([false, true])("keeps the old title until the save is acknowledged, grouped=%s", async grouped => {
    const user = userEvent.setup();
    let confirm!: () => void;
    const save = vi.fn(() => new Promise<void>(resolve => { confirm = resolve; }));
    const onSelect = vi.fn();
    render(<RenameCase save={save} grouped={grouped} onSelect={onSelect} />);
    const input = await startRename(user);
    expect(input).toHaveValue("Review");
    expect(input).toHaveAttribute("maxlength", "160");
    await user.clear(input); await user.type(input, "  Updated name  ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(save).toHaveBeenCalledExactlyOnceWith(topic.key, "Updated name");
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Updated name" })).not.toBeInTheDocument();
    await act(async () => confirm());
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Updated name" })).toBeVisible();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("retains a failed draft and retries without losing the entered name", async () => {
    const user = userEvent.setup();
    const save = vi.fn().mockRejectedValueOnce(new Error("write failed")).mockResolvedValue(undefined);
    render(<RenameCase save={save} />);
    const input = await startRename(user);
    await user.clear(input); await user.type(input, "  Keep this draft  ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("write failed");
    expect(input).toHaveValue("  Keep this draft  ");
    expect(input).toHaveAttribute("aria-invalid", "true");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Keep this draft" })).toBeVisible();
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("cancels an unsaved draft without switching conversations", async () => {
    const user = userEvent.setup();
    const save = vi.fn();
    const onSelect = vi.fn();
    render(<RenameCase save={save} onSelect={onSelect} />);
    const input = await startRename(user);
    await user.clear(input); await user.type(input, "Unconfirmed");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Review" })).toBeVisible();
    expect(save).not.toHaveBeenCalled(); expect(onSelect).not.toHaveBeenCalled();
  });

  it("rejects blank names and saves a completed IME draft through the form", async () => {
    const user = userEvent.setup();
    const save = vi.fn().mockResolvedValue(undefined);
    render(<RenameCase save={save} />);
    const input = await startRename(user);
    await user.clear(input); await user.type(input, "   ");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "新的会话" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(save).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(save).toHaveBeenCalledExactlyOnceWith(topic.key, "新的会话");
  });
});
