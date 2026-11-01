import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { Sidebar } from "@/components/Sidebar";
import { NodesSettings } from "@/components/settings/InstanceFeaturesSettings";
import { groupSessions } from "@/lib/chat-groups";
import { setAppLanguage } from "@/i18n";
import type { CirnoClient } from "@/lib/cirno-client";

const labels = {
  pinned: "Pinned",
  all: "Conversations",
  today: "Today",
  yesterday: "Yesterday",
  earlier: "Earlier",
  archived: "Archived",
  projects: "Projects",
  fallbackTitle: "New conversation",
};
const projects = [
  { id: "project-one", name: "One", working_directory: "/same" },
  { id: "project-two", name: "Two", working_directory: "/same" },
];
const sidebarProps = {
  sessions: [],
  activeKey: "websocket:global",
  loading: false,
  newChatActive: false,
  onNewChat: vi.fn(),
  onSelect: vi.fn(),
  onRequestDelete: vi.fn(),
  onTogglePin: vi.fn(),
  onRequestRename: vi.fn(),
  onToggleArchive: vi.fn(),
  onToggleGroup: vi.fn(),
  onRequestRenameProject: vi.fn(),
  onNewChatInProject: vi.fn(),
  onOpenSettings: vi.fn(),
  onOpenApps: vi.fn(),
  onOpenSkills: vi.fn(),
  onOpenAutomations: vi.fn(),
  onOpenChannels: vi.fn(),
  onOpenSearch: vi.fn(),
  onToggleArchived: vi.fn(),
} as ComponentProps<typeof Sidebar>;

afterEach(async () => {
  cleanup();
  await setAppLanguage("en");
});

it("keeps projects with the same directory distinct and preserves an empty project", () => {
  const groups = groupSessions(
    [
      {
        key: "websocket:one",
        channel: "websocket",
        chatId: "one",
        projectId: "project-one",
        preview: "",
        createdAt: null,
        updatedAt: null,
      },
    ],
    labels,
    {
      projects,
      pinnedKeys: [],
      archivedKeys: [],
      titleOverrides: {},
      projectNameOverrides: {},
      sessionOrder: [],
      showArchived: false,
      sort: "updated_desc",
    },
  );
  expect(
    groups.map((group) => [group.projectKey, group.sessions.length]),
  ).toEqual([
    ["project-one", 1],
    ["project-two", 0],
  ]);
});

it("uses the existing sidebar action styling, icons, and a single Projects heading", async () => {
  await act(() => setAppLanguage("en"));
  render(<Sidebar {...sidebarProps} projects={projects} />);
  const global = screen.getByRole("button", { name: "Cirno" });
  expect(global).toHaveAttribute("aria-current", "page");
  expect(global).toHaveClass("h-8", "text-[13px]");
  expect(global.querySelector("svg")).not.toBeNull();
  expect(screen.getAllByText("Projects")).toHaveLength(1);
  expect(
    screen.getByRole("button", { name: "One" }).querySelector("svg"),
  ).not.toBeNull();
  expect(screen.getByRole("button", { name: "Create project" })).toHaveClass(
    "h-6",
    "w-6",
  );
  expect(document.body.textContent).not.toMatch(/[\u4e00-\u9fff]/);
});

it("translates every new sidebar label when Chinese is selected", async () => {
  await act(() => setAppLanguage("zh-CN"));
  render(<Sidebar {...sidebarProps} projects={[]} />);
  expect(screen.getByRole("button", { name: "Cirno" })).toBeVisible();
  expect(screen.getByRole("button", { name: "创建项目" })).toBeVisible();
  expect(screen.getByText("项目", { exact: true })).toBeVisible();
  expect(screen.queryByText("Projects")).not.toBeInTheDocument();
});

it("provides a translated SSH-only Node configuration form", async () => {
  await act(() => setAppLanguage("en"));
  const requestMutation = vi.fn().mockResolvedValue({ nodes: [], jobs: [] });
  render(
    <NodesSettings client={{ requestMutation } as unknown as CirnoClient} />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Add Node" }));
  expect(screen.getByRole("textbox", { name: "SSH username" })).toBeVisible();
  expect(
    screen.getByRole("textbox", {
      name: "Private key path on the server (optional)",
    }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Read host fingerprints" }),
  ).toBeDisabled();
  expect(document.body.textContent).not.toMatch(/[\u4e00-\u9fff]/);
});


it("keeps pinned ordinary conversations first when explicit Projects are enabled", () => {
  const sessions = [
    { key: "websocket:new", channel: "websocket", chatId: "new", preview: "", createdAt: null, updatedAt: "2026-10-31T12:00:00Z" },
    { key: "websocket:pinned", channel: "websocket", chatId: "pinned", preview: "", createdAt: null, updatedAt: "2026-10-30T12:00:00Z" },
  ];
  const groups = groupSessions(sessions, labels, {
    projects: [], pinnedKeys: ["websocket:pinned"], archivedKeys: [],
    titleOverrides: {}, projectNameOverrides: {}, sessionOrder: [],
    showArchived: false, sort: "updated_desc",
  });
  expect(groups).toHaveLength(1);
  expect(groups[0].sessions.map(session => session.key)).toEqual(["websocket:pinned", "websocket:new"]);
});
