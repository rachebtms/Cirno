import { openAppConversation, closeAppConversationTab, startAppTemporaryConversation, visibleThreadRegion } from "./helpers/app-navigation";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import App from "@/App";
import { ThreadMessageCache } from "@/lib/thread-message-cache";
import { FilePreviewStore } from "@/hooks/useFilePreviewState";
import type { InboundEvent } from "@/lib/contracts/events";
import type { Outbound } from "@/lib/contracts/transport";
import { fetchBootstrap } from "@/lib/bootstrap";
import { canonicalThreadPayload } from "./thread-test-payload";

let withSecondConversation = false;
let withFiles = false;
const previewFile = (path: string) => ({
  path: `/workspace/${path}`,
  display_path: path,
  project_path: "/workspace",
  language: "text",
  content: `Preview of ${path}`,
  size: 20,
  truncated: false,
});

vi.mock("@/lib/bootstrap", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/bootstrap")>()),
  fetchBootstrap: vi.fn(async () => ({
    token: "test",
    api_token: "test",
    ws_path: "/",
  })),
  deriveWsUrl: () => "ws://test",
}));

// Only the network is fake: App, the workbench, stream hook and multiplexed client are real.
class TestSocket {
  static current: TestSocket;
  readyState = 0;
  sent: Outbound[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  private nextChat = 0;

  constructor() {
    TestSocket.current = this;
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  receive(event: InboundEvent) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(event) }),
    );
  }

  send(data: string) {
    const frame = JSON.parse(data) as Outbound;
    this.sent.push(frame);
    if (frame.type === "new_temporary_chat") {
      const chatId = `00000000-0000-4000-8000-${String(++this.nextChat).padStart(12, "0")}`;
      queueMicrotask(() =>
        this.receive({ event: "attached", chat_id: chatId, temporary: true, request_id: frame.request_id }),
      );
    } else if (frame.type === "set_sidebar_state") {
      queueMicrotask(() =>
        this.receive({ event: "sidebar_state_updated", state: frame.state }),
      );
    } else if (
      frame.type === "webui_request" &&
      frame.action === "workspace.files.read"
    ) {
      queueMicrotask(() =>
        this.receive({
          event: "webui_response",
          request_id: frame.request_id,
          ok: true,
          result: {
            ...previewFile(String(frame.payload.path)),
            kind: "text",
            editable: false,
            revision: "test",
          },
        }),
      );
    } else if (
      frame.type === "webui_request" &&
      frame.action === "temporary_chat.file_preview"
    ) {
      queueMicrotask(() =>
        this.receive({
          event: "webui_response",
          request_id: frame.request_id,
          ok: true,
          result: frame.payload.metadata
            ? {
                path: `/workspace/${String(frame.payload.path)}`,
                relative_path: frame.payload.path,
              }
            : frame.payload.probe
              ? { available: true }
              : previewFile(String(frame.payload.path)),
        }),
      );
    }
  }
}

async function startTemporaryChat(text: string) {
  await startAppTemporaryConversation(text);
  const chatId = window.location.hash.split("/").at(-1)!;
  await waitFor(() =>
    expect(
      within(visibleThreadRegion()).getByText(text),
    ).toBeInTheDocument(),
  );
  await waitFor(() =>
    expect(TestSocket.current.sent).toContainEqual(
      expect.objectContaining({
        type: "message",
        chat_id: chatId,
        content: text,
      }),
    ),
  );
  const frame = TestSocket.current.sent.find(
    (frame) => frame.type === "message" && frame.chat_id === chatId,
  );
  if (frame?.type !== "message") throw new Error("Missing submitted turn");
  act(() =>
    TestSocket.current.receive({
      event: "goal_status",
      chat_id: chatId,
      turn_id: frame.turn_id,
      status: "running",
      started_at: Date.now() / 1000,
    }),
  );
  return chatId;
}


describe("temporary chat navigation", () => {
  beforeAll(async () => {
    await Promise.all([
      import("@/features/settings/SettingsView"),
      import("@/components/thread/ThreadShell"),
    ]);
  });

  beforeEach(() => {
    vi.mocked(fetchBootstrap)
      .mockReset()
      .mockResolvedValue({ token: "test", api_token: "test", ws_path: "/" });
    withSecondConversation = false;
    withFiles = false;
    localStorage.clear();
    localStorage.setItem("cirno-webui.library", "1");
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
    vi.stubGlobal("WebSocket", TestSocket);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/v0/sessions") {
          return Response.json({
            sessions: ["regular", ...(withSecondConversation ? ["child"] : [])].map(
              (id) => ({
                key: `websocket:${id}`,
                title: id === "regular" ? "Regular topic" : "Second pane",
                created_at: "2026-09-01T00:00:00Z",
                updated_at: "2026-09-01T00:00:00Z",
              }),
            ),
          });
        }
        if (path === "/v0/webui/sidebar-state") return Response.json({});
        if (path.includes("/file-preview?")) {
          const query = new URL(path, "http://test").searchParams;
          if (query.has("metadata"))
            return Response.json({
              path: `/workspace/${query.get("path")}`,
              relative_path: query.get("path"),
            });
          return Response.json(
            query.has("probe")
              ? { available: true }
              : previewFile(query.get("path")!),
          );
        }
        if (withFiles && path.includes("/webui-thread")) {
          return Response.json(
            canonicalThreadPayload({
              schemaVersion: 3,
              messages: [
                {
                  id: "file-reply",
                  role: "assistant",
                  createdAt: 1,
                  content:
                    "Files: [notes.txt](notes.txt) and [second.txt](second.txt). [Website](https://example.com/demo)",
                },
              ],
            }),
          );
        }
        return new Response(null, { status: 404 });
      }),
    );
  });

  afterEach(() => {
    cleanup();
    if (vi.isFakeTimers()) vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each(["settings", "apps", "automations", "skills", "channels"])(
    "opens %s directly without mounting chat or retaining a chat query",
    async (view) => {
      window.history.replaceState(
        null,
        "",
        `/#/${view}?chat=websocket%3Aregular`,
      );
      render(<App />);
      await screen.findByRole("button", { name: "Open New conversation" });
      act(() => TestSocket.current.open());
      await waitFor(() => expect(window.location.hash).toBe(`#/${view}`));
      expect(window.history.state.cirnoReturnChat.key).toBe(
        "websocket:regular",
      );
      expect(
        screen.queryByTestId("thread-message-region"),
      ).not.toBeInTheDocument();
      const requests = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
      expect(
        requests.filter(
          (url) => url.includes("/webui-thread") || url === "/v0/commands",
        ),
      ).toEqual([]);
    },
  );

  it("restores the return destination after refreshing a clean settings URL", async () => {
    const first = render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    await openAppConversation("Regular topic");
    fireEvent.click(screen.getByRole("button", { name: "Open Settings" }));
    await screen.findByRole("navigation", { name: "Settings sections" });
    expect(window.location.hash).toBe("#/settings");
    first.unmount();
    vi.mocked(fetch).mockClear();
    render(<App />);
    await screen.findByRole("navigation", { name: "Settings sections" });
    act(() => TestSocket.current.open());
    expect(
      vi
        .mocked(fetch)
        .mock.calls.filter(([url]) => String(url).includes("/webui-thread")),
    ).toEqual([]);
    fireEvent.click(screen.getByRole("tab", { name: "Regular topic" }));
    await waitFor(() =>
      expect(window.location.hash).toBe("#/chat/websocket%3Aregular"),
    );
    await waitFor(() =>
      expect(
        vi
          .mocked(fetch)
          .mock.calls.some(([url]) => String(url).includes("/webui-thread")),
      ).toBe(true),
    );
  });

  it("returns from settings to the same temporary chat and keeps its live messages", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    const chatId = await startTemporaryChat("Temporary navigation check");
    fireEvent.click(screen.getByRole("button", { name: "Open Settings" }));
    await screen.findByRole("navigation", { name: "Settings sections" });
    expect(window.location.hash).toBe("#/settings");
    act(() =>
      TestSocket.current.receive({
        event: "message",
        chat_id: chatId,
        text: "Reply while in settings",
      }),
    );
    fireEvent.click(screen.getAllByRole("tab").find(tab => tab.getAttribute("aria-selected") !== "true" && tab.textContent?.includes("Temporary navigation check"))!);
    await waitFor(() =>
      expect(window.location.hash).toBe(`#/temporary/${chatId}`),
    );
    await screen.findByText("Reply while in settings");
    expect(
      vi
        .mocked(fetch)
        .mock.calls.filter(([url]) => String(url).includes(chatId)),
    ).toEqual([]);
  });

  it("keeps an independent file tab stable across bootstrap token refresh", async () => {
    withFiles = true;
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchBootstrap)
      .mockResolvedValueOnce({
        token: "old",
        api_token: "old",
        ws_path: "/",
        expires_in: 30,
      })
      .mockResolvedValue({
        token: "renewed",
        api_token: "renewed",
        ws_path: "/",
        expires_in: 300,
      });
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    await openAppConversation("Regular topic");
    fireEvent.click(await screen.findByRole("button", { name: "notes.txt" }));
    await screen.findByText("Preview of notes.txt");
    const panel = screen.getByTestId("file-preview-panel");
    const fileRequests = () =>
      TestSocket.current.sent.filter(
        (frame) =>
          frame.type === "webui_request" &&
          frame.action === "workspace.files.read",
      );
    expect(fileRequests()).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(fetchBootstrap).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("file-preview-panel")).toBe(panel);
    expect(fileRequests()).toHaveLength(1);
    await openAppConversation("Regular topic");
    await waitFor(() =>
      expect(panel).not.toBeVisible(),
    );
    fireEvent.click(screen.getByRole("button", { name: "second.txt" }));
    await screen.findByText("Preview of second.txt");
    expect(fileRequests()).toHaveLength(2);
    fireEvent.click(screen.getByRole("tab", { name: "notes.txt" }));
    await waitFor(() => expect(screen.getByTestId("file-preview-panel")).toBeVisible());
    expect(screen.getByText("Preview of notes.txt")).toBeVisible();
    expect(fileRequests()).toHaveLength(2);
  });

  it.each([true])(
    "restores temporary file previews after pane navigation (temporary=%s)",
    async (temporary) => {
      withFiles = true;
      withSecondConversation = true;
      vi.stubGlobal("matchMedia", (query: string) => ({
        matches: query.includes("max-width: 767px"),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }));
      render(<App />);
      await screen.findByRole("button", { name: "Temporary chat" });
      act(() => TestSocket.current.open());
      if (temporary) {
        const chatId = await startTemporaryChat("Show example files");
        act(() =>
          TestSocket.current.receive({
            event: "message",
            chat_id: chatId,
            text: "Files: [notes.txt](notes.txt) and [second.txt](second.txt)",
          }),
        );
      } else {
        await openAppConversation("Regular topic");
      }
      fireEvent.contextMenu(
        await screen.findByRole("button", { name: "notes.txt" }),
      );
      await waitFor(() =>
        expect(
          screen.getByRole("menuitem", { name: "Copy absolute path" }),
        ).not.toHaveAttribute("data-disabled"),
      );
      if (temporary) {
        expect(TestSocket.current.sent).toContainEqual(
          expect.objectContaining({
            type: "webui_request",
            action: "temporary_chat.file_preview",
            payload: expect.objectContaining({
              path: "notes.txt",
              metadata: true,
            }),
          }),
        );
      } else {
        expect(
          vi
            .mocked(fetch)
            .mock.calls.some(([url]) =>
              String(url).includes("path=notes.txt&metadata=1"),
            ),
        ).toBe(true);
      }
      fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
      await waitFor(() =>
        expect(screen.queryByRole("menu")).not.toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole("button", { name: "notes.txt" }));
      await screen.findByText("Preview of notes.txt");
      fireEvent.click(screen.getByRole("button", { name: "second.txt" }));
      await screen.findByText("Preview of second.txt");
      const pane = screen.getByTestId("preview-pane");
      expect(within(pane).getAllByText("second.txt")).toHaveLength(1);
      expect(
        within(pane).queryByRole("navigation", { name: "File path" }),
      ).not.toBeInTheDocument();
      expect(
        within(pane).queryByRole("button", { name: /File actions/ }),
      ).not.toBeInTheDocument();
      fireEvent.contextMenu(
        within(pane).getByRole("tab", { name: "second.txt" }),
      );
      await waitFor(() =>
        expect(
          screen.getByRole("menuitem", { name: "Copy absolute path" }),
        ).not.toHaveAttribute("data-disabled"),
      );
      if (temporary) {
        expect(TestSocket.current.sent).toContainEqual(
          expect.objectContaining({
            type: "webui_request",
            action: "temporary_chat.file_preview",
            payload: expect.objectContaining({
              path: "second.txt",
              metadata: true,
            }),
          }),
        );
      } else {
        expect(
          vi
            .mocked(fetch)
            .mock.calls.some(([url]) =>
              String(url).includes("path=second.txt&metadata=1"),
            ),
        ).toBe(true);
      }
      fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
      await waitFor(() =>
        expect(screen.queryByRole("menu")).not.toBeInTheDocument(),
      );
      expect(screen.getByTestId("preview-pane")).toBe(pane);
      const previewRequestCount = () =>
        temporary
          ? TestSocket.current.sent.filter(
              (frame) =>
                frame.type === "webui_request" &&
                frame.action === "temporary_chat.file_preview" &&
                frame.payload?.path === "notes.txt" &&
                !frame.payload?.metadata &&
                !frame.payload?.probe,
            ).length
          : vi
              .mocked(fetch)
              .mock.calls.filter(
                ([url]) =>
                  String(url).includes("/file-preview?path=notes.txt") &&
                  !String(url).includes("metadata=") &&
                  !String(url).includes("probe="),
              ).length;
      const beforeReturn = previewRequestCount();
      fireEvent.click(screen.getByRole("tab", { name: "notes.txt" }));
      expect(screen.getByText("Preview of notes.txt")).toBeInTheDocument();
      expect(previewRequestCount()).toBe(beforeReturn);
      await openAppConversation("Second pane");
      expect(
        screen.queryByTestId("file-preview-panel"),
      ).not.toBeVisible();
      await openAppConversation(temporary ? "Show example files" : "Regular topic");
      await screen.findByText("Preview of notes.txt");
      expect(
        within(screen.getByTestId("preview-pane")).getAllByRole("tab"),
      ).toHaveLength(2);
      expect(screen.getByRole("tab", { name: "notes.txt" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      expect(
        screen.queryByText("Preview of second.txt"),
      ).not.toBeInTheDocument();

      // Explicit close must stick even if switching interrupts the close animation.
      fireEvent.click(
        screen.getByRole("button", { name: "Close preview pane" }),
      );
      await openAppConversation("Second pane");
      await openAppConversation(temporary ? "Show example files" : "Regular topic");
      expect(
        screen.queryByTestId("file-preview-panel"),
      ).not.toBeInTheDocument();

      if (temporary) {
        const requests = vi
          .mocked(fetch)
          .mock.calls.map(([url]) => String(url));
        expect(requests.some((url) => url.includes("00000000-"))).toBe(false);
      }
      for (const storage of [localStorage, sessionStorage]) {
        const values = Array.from({ length: storage.length }, (_, i) =>
          storage.getItem(storage.key(i)!),
        );
        expect(JSON.stringify(values)).not.toContain("/workspace/notes.txt");
        expect(JSON.stringify(values)).not.toContain("Preview of notes.txt");
      }
    },
  );

  it("opens independent files as workspace tabs and closes only the chosen tab", async () => {
    withFiles = true;
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    await openAppConversation("Regular topic");
    fireEvent.click(await screen.findByRole("button", { name: "notes.txt" }));
    await screen.findByText("Preview of notes.txt");
    await openAppConversation("Regular topic");
    fireEvent.click(screen.getByRole("button", { name: "second.txt" }));
    await screen.findByText("Preview of second.txt");
    fireEvent.click(screen.getByRole("button", { name: "Close second.txt" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("tab", { name: "second.txt" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("tab", { name: "notes.txt" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "notes.txt" }));
    expect(screen.getByTestId("file-preview-panel")).toBeVisible();
    expect(screen.getByText("Preview of notes.txt")).toBeVisible();
    expect(screen.queryByTestId("preview-pane")).not.toBeInTheDocument();
  });

  it("forgets preview paths on temporary close and disconnect", async () => {
    const update = vi.spyOn(FilePreviewStore.prototype, "open");
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    const chatId = await startTemporaryChat("Show example files");
    act(() =>
      TestSocket.current.receive({
        event: "message",
        chat_id: chatId,
        text: "[notes.txt](notes.txt)",
      }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "notes.txt" }));
    await screen.findByText("Preview of notes.txt");
    const store = update.mock.contexts.find(
      (value): value is FilePreviewStore =>
        value instanceof FilePreviewStore &&
        value.get(`websocket:${chatId}`).tabs.length > 0,
    )!;
    expect(store.get(`websocket:${chatId}`).activeId).toBe("file:notes.txt");
    await closeAppConversationTab("Show example files");
    expect(store.get(`websocket:${chatId}`).tabs).toEqual([]);
    act(() => store.open("websocket:regular", "notes.txt"));
    vi.useFakeTimers();
    act(() => TestSocket.current.close());
    expect(store.get("websocket:regular").tabs).toEqual([]);
  });

  it("keeps messages when navigating to a regular workbench and back", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    const chatId = await startTemporaryChat("Count from one to three");

    await openAppConversation("Regular topic");
    await waitFor(() =>
      expect(window.location.hash).toBe("#/chat/websocket%3Aregular"),
    );
    await openAppConversation("Count from one to three");
    await waitFor(() =>
      expect(window.location.hash).toBe(`#/temporary/${chatId}`),
    );

    expect(
      within(visibleThreadRegion()).getByText(
        "Count from one to three",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("hero-greeting")).not.toBeInTheDocument();
  });

  it.each(["before leaving", "while away", "after returning"])(
    "preserves streamed output when the turn finishes %s",
    async (completion) => {
      render(<App />);
      await screen.findByRole("button", { name: "Temporary chat" });
      act(() => TestSocket.current.open());
      const chatId = await startTemporaryChat("Count from one to three");
      const socket = TestSocket.current;
      const turnId = socket.sent.find(
        (frame) => frame.type === "message",
      )?.turn_id;
      const emit = (event: InboundEvent) => act(() => socket.receive(event));
      const finish = () => {
        emit({
          event: "delta",
          chat_id: chatId,
          turn_id: turnId,
          text: " two three",
        });
        emit({ event: "stream_end", chat_id: chatId, turn_id: turnId });
        emit({ event: "turn_end", chat_id: chatId, turn_id: turnId });
      };
      emit({ event: "delta", chat_id: chatId, turn_id: turnId, text: "one" });
      await screen.findByText("one");
      if (completion === "before leaving") finish();

      await openAppConversation("Regular topic");
      if (completion === "while away") finish();
      await openAppConversation("Count from one to three");
      if (completion === "after returning") {
        expect(
          screen.getByRole("button", { name: "Stop response" }),
        ).toBeInTheDocument();
        finish();
      }

      await waitFor(() =>
        expect(
          within(visibleThreadRegion()).getAllByText(
            "one two three",
          ),
        ).toHaveLength(1),
      );
      expect(
        within(visibleThreadRegion()).getAllByText(
          "Count from one to three",
        ),
      ).toHaveLength(1);
      expect(
        screen.queryByRole("button", { name: "Stop response" }),
      ).not.toBeInTheDocument();
    },
  );

  it("keeps temporary messages when switching between retained mobile tabs", async () => {
    withSecondConversation = true;
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width: 767px"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    await startTemporaryChat("Count from one to three");
    await openAppConversation("Second pane");
    await openAppConversation("Count from one to three");
    expect(
      within(visibleThreadRegion()).getByText(
        "Count from one to three",
      ),
    ).toBeInTheDocument();
  });

  it("retains deltas received just before switching away, before the next paint", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    const chatId = await startTemporaryChat("Count from one to three");
    const turnId = TestSocket.current.sent.find(
      (frame) => frame.type === "message",
    )?.turn_id;
    fireEvent.click(screen.getByRole("button", { name: "Open Conversations" }));
    const destination = await screen.findByRole("button", { name: "Regular topic" });
    act(() => {
      TestSocket.current.receive({
        event: "delta",
        chat_id: chatId,
        turn_id: turnId,
        text: "one",
      });
      fireEvent.click(destination);
    });
    await openAppConversation("Count from one to three");
    await waitFor(() =>
      expect(
        within(visibleThreadRegion()).getAllByText("one"),
      ).toHaveLength(1),
    );
  });

  it.each(["stream_end", "turn_end", "message"] as const)(
    "retains a received %s when navigation hides the tab before React commits",
    async (event) => {
      withSecondConversation = true;
      vi.stubGlobal("matchMedia", (query: string) => ({
        matches: query.includes("max-width: 767px"),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }));
      render(<App />);
      await screen.findByRole("button", { name: "Temporary chat" });
      act(() => TestSocket.current.open());
      const chatId = await startTemporaryChat("Count from one to three");
      const turnId = TestSocket.current.sent.find(
        (frame) => frame.type === "message",
      )?.turn_id;
      fireEvent.click(screen.getByRole("button", { name: "Open Conversations" }));
      const destination = await screen.findByRole("button", { name: "Second pane" });
      act(() => {
        if (event !== "message") {
          TestSocket.current.receive({
            event: "delta",
            chat_id: chatId,
            turn_id: turnId,
            text: "one two three",
          });
        }
        TestSocket.current.receive({
          event,
          chat_id: chatId,
          turn_id: turnId,
          text: "one two three",
        });
        fireEvent.click(destination);
      });
      await openAppConversation("Count from one to three");
      const region = visibleThreadRegion();
      expect(region.textContent).toContain("one two three");
      expect(within(region).getAllByText("one two three")).toHaveLength(1);
      expect(
        within(region).getAllByText("Count from one to three"),
      ).toHaveLength(1);
      if (event === "turn_end") {
        expect(
          screen.queryByRole("button", { name: "Stop response" }),
        ).not.toBeInTheDocument();
      }
    },
  );

  it("keeps multiple temporary chats isolated and releases the closed chat's cache", async () => {
    const deleteCache = vi.spyOn(ThreadMessageCache.prototype, "delete");
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    const firstChatId = await startTemporaryChat("Count from one to three");
    const firstTurnId = TestSocket.current.sent.find(
      (frame) => frame.type === "message",
    )?.turn_id;
    await openAppConversation("New conversation");
    const secondChatId = await startTemporaryChat("List three colors");
    act(() => {
      TestSocket.current.receive({
        event: "delta",
        chat_id: firstChatId,
        turn_id: firstTurnId,
        text: "one two three",
      });
      TestSocket.current.receive({
        event: "turn_end",
        chat_id: firstChatId,
        turn_id: firstTurnId,
      });
    });
    expect(within(visibleThreadRegion()).queryByText("one two three")).not.toBeInTheDocument();
    await openAppConversation("Regular topic");
    await openAppConversation("Count from one to three");
    await waitFor(() =>
      expect(
        within(visibleThreadRegion()).getAllByText(
          "one two three",
        ),
      ).toHaveLength(1),
    );
    expect(
      within(visibleThreadRegion()).queryByText(
        "List three colors",
      ),
    ).not.toBeInTheDocument();
    await openAppConversation("List three colors");
    expect(
      within(visibleThreadRegion()).getAllByText(
        "List three colors",
      ),
    ).toHaveLength(1);

    await closeAppConversationTab("Count from one to three");
    expect(deleteCache).toHaveBeenCalledWith(firstChatId);
    expect(TestSocket.current.sent).toContainEqual({
      type: "discard_temporary_chat",
      chat_id: firstChatId,
    });
    expect(window.location.hash).toBe(`#/temporary/${secondChatId}`);
    await closeAppConversationTab("List three colors");
    expect(deleteCache).toHaveBeenCalledWith(secondChatId);
    await waitFor(() => expect(screen.queryByRole("tab", { name: "List three colors" })).not.toBeInTheDocument());
    expect(screen.queryByRole("tab", { name: "Count from one to three" })).not.toBeInTheDocument();
    await openAppConversation("Regular topic");
    expect(screen.getByRole("tab", { name: "Regular topic" })).toHaveAttribute("aria-selected", "true");
    for (const cache of deleteCache.mock.contexts) {
      if (!(cache instanceof ThreadMessageCache))
        throw new Error("Expected thread message cache");
      expect(cache.get(firstChatId)).toBeUndefined();
      expect(cache.get(secondChatId)).toBeUndefined();
    }

    // No history reads, sidebar persistence or browser storage may contain these chats.
    const requests = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    for (const chatId of [firstChatId, secondChatId]) {
      expect(requests.some((url) => url.includes(chatId))).toBe(false);
      expect(
        JSON.stringify(
          TestSocket.current.sent.filter(
            (frame) => frame.type === "set_sidebar_state",
          ),
        ),
      ).not.toContain(chatId);
    }
    for (const storage of [localStorage, sessionStorage]) {
      const values = Array.from({ length: storage.length }, (_, index) =>
        storage.getItem(storage.key(index)!),
      );
      expect(JSON.stringify(values)).not.toMatch(
        /Count from one to three|List three colors|one two three/,
      );
    }
    deleteCache.mockRestore();
  });

  it("still ends temporary chats and clears their cache on disconnect", async () => {
    const deleteCache = vi.spyOn(ThreadMessageCache.prototype, "delete");
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    const chatId = await startTemporaryChat("Count from one to three");
    await openAppConversation("Regular topic");
    // Do not let the synthetic disconnected client reconnect after teardown.
    vi.useFakeTimers();
    await act(async () => TestSocket.current.close());
    expect(deleteCache).toHaveBeenCalledWith(chatId);
    for (const cache of deleteCache.mock.contexts) {
      if (!(cache instanceof ThreadMessageCache))
        throw new Error("Expected thread message cache");
      expect(cache.get(chatId)).toBeUndefined();
    }
    expect(
      screen.queryByRole("button", { name: "Count from one to three" }),
    ).not.toBeInTheDocument();
    deleteCache.mockRestore();
  });

  it("does not truncate a temporary reply that keeps streaming while away", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Temporary chat" });
    act(() => TestSocket.current.open());
    const chatId = await startTemporaryChat("Count from one to three");
    const turnId = TestSocket.current.sent.find(
      (frame) => frame.type === "message",
    )?.turn_id;
    await openAppConversation("Regular topic");
    const chunks = Array.from({ length: 2_010 }, (_, index) => `word${index} `);
    act(() => {
      for (const text of chunks) {
        TestSocket.current.receive({
          event: "delta",
          chat_id: chatId,
          turn_id: turnId,
          text,
        });
      }
      TestSocket.current.receive({
        event: "turn_end",
        chat_id: chatId,
        turn_id: turnId,
      });
    });
    await openAppConversation("Count from one to three");
    await waitFor(() =>
      expect(
        within(visibleThreadRegion()).getAllByText(
          chunks.join("").trim(),
        ),
      ).toHaveLength(1),
    );
  });
});
