import type { WorkspaceModule } from "@/features/workbench/contracts";
import { Globe } from "lucide-react";
import { lazy } from "react";
const BrowserTab = lazy(() => import("./BrowserTab").then((module) => ({ default: module.BrowserTab })));
export const browserModule: WorkspaceModule = {
  id: "browser", panels: [
    { kind: "browser", titleKey: "workspace.browser", Icon: Globe, Content: BrowserTab, tabPolicy: "multiple", showInMenu: true },
  ]
};
