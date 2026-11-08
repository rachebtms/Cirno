import type { WorkspaceModule } from "@/features/workbench/contracts";
import { Library } from "lucide-react";
import { lazy } from "react";
const Content = lazy(() =>
  import("./ConversationsPage").then((module) => ({
    default: module.ConversationsPage,
  })),
);
export const conversationsModule: WorkspaceModule = {
  id: "conversations",
  panels: [
    {
      kind: "conversations",
      titleKey: "workspace.library",
      Icon: Library,
      Content,
      tabPolicy: "single", showInMenu: true,
    },
  ],
};
