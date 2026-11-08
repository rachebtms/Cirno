import { SettingsRebuildFixture } from "./settings-rebuild-fixture";
import { useTheme } from "@/hooks/useTheme";
import {
  ConversationCatalogContext,
  type ConversationCatalog,
} from "@/features/conversations/catalog/context";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Workbench } from "@/features/workbench/Workbench";
import type { WorkspaceRoute } from "@/features/workbench/contracts";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { useReadingTypography } from "@/hooks/useReadingTypography";
import type { CirnoClient } from "@/lib/cirno-client";

async function sampleVideo() {
  const canvas = document.createElement("canvas");
  canvas.width = 160;
  canvas.height = 90;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas is unavailable in the video fixture");
  context.fillStyle = "#215b79";
  context.fillRect(0, 0, 160, 90);
  const stream = canvas.captureStream(10);
  const recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
  const chunks: BlobPart[] = [];
  return new Promise<string>((resolve, reject) => {
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onerror = () => {
      stream.getTracks().forEach((track) => track.stop());
      reject(new Error("Fixture video recording failed"));
    };
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      resolve(URL.createObjectURL(new Blob(chunks, { type: "video/webm" })));
    };
    recorder.start();
    let frame = 0;
    const draw = window.setInterval(() => {
      context.fillStyle = "#b5e5f1";
      context.fillRect(20 + frame++ * 2, 20, 50, 50);
    }, 60);
    window.setTimeout(() => {
      window.clearInterval(draw);
      recorder.stop();
    }, 650);
  });
}

export function WorkspaceFixture() {
  useTheme();
  useReadingTypography();
  const { t } = useTranslation();
  const [route, setRoute] = useState<WorkspaceRoute>({
    view: "chat",
    activeKey: "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
    settingsSection: "overview",
  });
  const [sequence, setSequence] = useState(0);
  const [projects, setProjects] = useState([
    { id: "research", name: "Research project" },
  ]);
  const [preferences, setPreferences] = useState<
    NonNullable<ConversationCatalog["preferences"]>
  >({
    pinned_keys: [],
    archived_keys: [],
    title_overrides: {},
    session_order: [],
    view: {
      sort: "updated_desc",
      density: "comfortable",
      show_archived: false,
    },
  });
  const sessions: ChatSummary[] = [
    {
      key: "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
      role: "router",
      channel: "websocket",
      chatId: "b1ec9323-2155-5f24-bc56-1da2f59aeecb",
      createdAt: null,
      updatedAt: null,
      title: "Cirno",
      preview: "",
    },
    {
      key: "websocket:worker",
      projectId: "research",
      channel: "websocket",
      chatId: "worker",
      createdAt: null,
      updatedAt: null,
      title: "Research worker",
      preview: "Verified observations",
    },
  ];
  if (new URLSearchParams(location.search).has("catalogStress")) {
    sessions.push({
      ...sessions[1],
      key: "websocket:independent",
      chatId: "independent",
      projectId: undefined,
      title: "Independent review",
    });
    sessions.push(
      ...Array.from({ length: 45 }, (_, index) => ({
        ...sessions[1],
        key: `websocket:experiment-${index}`,
        chatId: `experiment-${index}`,
        title: `Experiment ${String(index).padStart(2, "0")}`,
      })),
    );
  }
  const client = useMemo(() => {
    let content = "# Research notes\n\nVerified observations and next steps.\n";
    let terminalAttempts = 0;
    let video: Promise<string> | null = null;
    let recordingRunning = true,
      recordingEpoch = "fixture-epoch",
      recordingCleared = false;
    return {
      requestMutation: async (
        action: string,
        payload: Record<string, unknown>,
      ) => {
        if (action === "instance.action")
          return { nodes: [{ id: "fixture-node", name: "Research Node" }] };
        if (action === "workspace.files.list")
          return {
            path: "/workspace",
            project_path: "/workspace",
            parent: null,
            entries: [
              { name: "notes.md", path: "/workspace/notes.md", kind: "file" },
              {
                name: "recording.webm",
                path: "/workspace/recording.webm",
                kind: "file",
              },
              {
                name: "experiments",
                path: "/workspace/experiments",
                kind: "directory",
              },
            ],
            truncated: false,
          };
        if (
          action === "workspace.files.read" &&
          payload.path === "/workspace/recording.webm"
        )
          return {
            kind: "video",
            path: payload.path,
            display_path: "recording.webm",
            project_path: "/workspace",
            size: 2048,
            mime_type: "video/webm",
            url: await (video ??= sampleVideo()),
            editable: false,
            revision: null,
          };
        if (action === "workspace.files.save")
          content = payload.content as string;
        if (
          action === "workspace.files.read" ||
          action === "workspace.files.save"
        )
          return {
            kind: "text",
            path: "/workspace/notes.md",
            display_path: "notes.md",
            project_path: "/workspace",
            content,
            language: "markdown",
            truncated: false,
            editable: true,
            revision: "v1",
          };
        const values = payload.values as Record<string, unknown> | undefined;
        if (
          [
            "trace.create",
            "trace.start",
            "trace.pause",
            "trace.clear",
            "trace.close",
          ].includes(String(payload.action))
        ) {
          if (payload.action === "trace.start") recordingRunning = true;
          if (payload.action === "trace.pause") recordingRunning = false;
          if (payload.action === "trace.clear") {
            recordingCleared = true;
            recordingEpoch = "after-clear";
          }
          return {
            id: values?.recording_id,
            running: recordingRunning,
            epoch: recordingEpoch,
            count: recordingCleared ? 0 : 31,
            created_ms: 1793836800000,
            reason: null,
          };
        }
        if (payload.action === "trace.events") {
          const events = values?.before
            ? [
                {
                  id: 1,
                  session_key: "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
                  kind: "input",
                  created_ms: 1793836700000,
                  summary: "Earlier task",
                  status: "",
                  turn_id: "turn-0",
                },
              ]
            : [
                {
                  id: 32,
                  kind: "request",
                  session_key: "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
                  created_ms: 1793836809000,
                  summary: "DeepSeek",
                  status: "completed",
                  turn_id: null,
                },
                ...Array.from({ length: 30 }, (_, i) => ({
                  id: 31 - i,
                  kind: [
                    "answer_segment",
                    "tool_activity",
                    "reasoning_segment",
                    "compaction",
                    "input",
                    "completion",
                  ][i % 6],
                  session_key:
                    i % 2 ? "websocket:research-worker" : "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
                  created_ms: 1793836808000 - i * 211,
                  summary: [
                    "The results are ready.",
                    "nodes.execute",
                    "Comparing experiment outcomes and checking numerical evidence.",
                    "Context threshold reached; checkpoint saved.",
                    "Review the results.",
                    "Turn completed",
                  ][i % 6],
                  status: [
                    "answer",
                    "end",
                    "reasoning",
                    "succeeded",
                    "user",
                    "completed",
                  ][i % 6],
                  turn_id: "turn-01",
                  bytes: 1200 + i * 37,
                })),
              ];
          const kinds: Record<string, string> = {
            tool: "tool_activity",
            request: "request",
            input: "input",
          };
          const filtered = events.filter(
            (event) =>
              (!values?.kind || event.kind === kinds[String(values.kind)]) &&
              (!values?.session_key ||
                values.session_key === event.session_key),
          );
          return {
            id: values?.recording_id,
            running: recordingRunning,
            epoch: recordingEpoch,
            count: recordingCleared ? 0 : 31,
            created_ms: 1793836800000,
            reason: null,
            events: recordingCleared ? [] : filtered,
            sources: ["websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "websocket:research-worker"],
            before: values?.before || recordingCleared ? null : 2,
          };
        }
        if (payload.action === "trace.detail" && values?.event_id !== 32)
          return {
            event: {
              kind: "tool_activity",
              content: {
                tool_events: [
                  {
                    name: "nodes.execute",
                    phase: "end",
                    arguments: { command: "uname -a" },
                    result: "Linux research-node",
                  },
                ],
              },
              turn_id: "turn-01",
            },
          };
        if (payload.action === "trace.detail")
          return {
            messages: [
              {
                role: "system",
                content: "You are Cirno, the owner's personal research agent.",
              },
              { role: "user", content: "Review the results." },
            ],
            offset: 0,
            total: 2,
            tools: [{ name: "memory.search" }],
            response: { content: "The results are ready." },
            status: "completed",
          };
        if (payload.action === "credentials.list")
          return {
            records: [
              {
                id: "credential-1",
                label: "Research account",
                kind: "password",
              },
            ],
          };
        if (payload.action === "terminal.create") {
          if (++terminalAttempts === 1 && new URLSearchParams(location.search).has("terminalFailure"))
            throw new Error("SSH authentication failed: verify the Node credentials.");
          return { id: values?.key };
        }
        if (payload.action === "terminal.read")
          return {
            data: values?.cursor ? "" : "Cirno terminal\r\n/workspace $ ",
            cursor: 35,
            reset: false,
            exit_code: null,
          };
        return { ok: true };
      },
    } as unknown as CirnoClient;
  }, []);
  const navigate = (next: WorkspaceRoute) => {
    setRoute(next);
    setSequence((old) => old + 1);
  };
  return (
    <div
      style={{ height: "100dvh", width: "100vw" }}
      className="overflow-hidden bg-background text-foreground"
    >
      <ConversationCatalogContext.Provider
        value={{
          owner: client,
          sessions,
          projects,
          loading: false,
          open: (key) =>
            navigate({
              view: "chat",
              activeKey: key,
              settingsSection: "overview",
            }),
          create: () =>
            navigate({
              view: "chat",
              activeKey: null,
              settingsSection: "overview",
            }),
          saveProject: async (draft) => {
            setProjects((old) => [...old, { ...draft, id: draft.id ?? draft.name }]);
          },
          deleteProject: async () => undefined,
          assign: () => undefined,
          preferences,
          showArchived: preferences.view?.show_archived ?? false,
          toggleArchived: () =>
            setPreferences((old) => ({
              ...old,
              view: { ...old.view!, show_archived: !old.view?.show_archived },
            })),
          rename: async () => undefined,
          togglePin: () => undefined,
          toggleArchive: () => undefined,
          deleteConversation: () => undefined,
          deleteMany: (_items, decision) => decision?.(false),
          archiveMany: (keys, archive) =>
            setPreferences((old) => ({
              ...old,
              archived_keys: archive
                ? [...new Set([...old.archived_keys, ...keys])]
                : old.archived_keys.filter((key) => !keys.includes(key)),
            })),
          setSort: (sort) =>
            setPreferences((old) => ({ ...old, view: { ...old.view!, sort } })),
        }}
      >
        <Workbench
          client={client}
          route={route}
          navigationSequence={sequence}
          title={
            route.activeKey === "websocket:worker" ? "Research worker" : "Cirno"
          }
          sessions={sessions}
          scope={{ project_path: "/workspace", access_mode: "full" }}
          onRoute={navigate}
          onNewChat={() =>
            navigate({
              view: "chat",
              activeKey: "websocket:worker",
              settingsSection: "overview",
            })
          }
          beforeActivate={(action) => action()}
          onRouteVisibleChange={() => {}}
          renderRoute={(tabRoute) => (
          <div data-fixture-session={tabRoute.activeKey} className="absolute inset-0 flex min-h-0 flex-col">
            {tabRoute.view === "chat" ? (
              <>
                <div className="min-h-0 flex-1 overflow-auto">
                  <div className="mx-auto max-w-3xl px-5 py-8">
                    <ThreadMessages
                      defaultActivityCollapsed={
                        tabRoute.activeKey === "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
                      }
                      assistantBubbles={tabRoute.activeKey === "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"}
                      messages={[
                        {
                          id: "u1",
                          role: "user",
                          content:
                            "Review the experiment results and prepare a report.",
                          createdAt: 1793836800000,
                        },
                        {
                          id: "a1",
                          role: "assistant",
                          content: "I am checking the experiment results.",
                          createdAt: 1793836801000,
                        },
                        {
                          id: "a2",
                          role: "assistant",
                          content:
                            "The experiment completed. Verified steps are in **notes.md**.",
                          createdAt: 1793836803000,
                        },
                        {
                          id: "a3",
                          role: "assistant",
                          content:
                            "A background check found one result ready for review.",
                          createdAt: 1793836860000,
                        },
                      ]}
                      isStreaming={false}
                    />
                  </div>
                </div>
                <div className="mx-auto w-full max-w-3xl px-4 pb-4">
                  <ThreadComposer onSend={() => {}} workspaceControlsHidden />
                </div>
              </>
            ) : (
              new URLSearchParams(location.search).has("paneSettings") ? <SettingsRebuildFixture embedded /> : <div className="flex flex-1 items-center justify-center">
                {t("workspace.settings")}
              </div>
            )}
          </div>
          )}
        />
      </ConversationCatalogContext.Provider>
    </div>
  );
}
