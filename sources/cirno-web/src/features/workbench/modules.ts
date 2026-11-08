import { browserModule } from "@/features/browser/module";
import { conversationsModule } from "@/features/conversations/module";
import { credentialsModule } from "@/features/credentials/module";
import { filesModule } from "@/features/files/module";
import { terminalModule } from "@/features/terminal/module";
import { traceModule } from "@/features/trace/module";
import { createWorkspaceRegistry } from "./registry";

export const workspacePanels = createWorkspaceRegistry([
  conversationsModule, filesModule, terminalModule, browserModule, traceModule, credentialsModule,
]);
