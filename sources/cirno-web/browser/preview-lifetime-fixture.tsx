import { useState } from "react";
import { useTheme } from "@/hooks/useTheme";
import { useThreadPreview } from "@/components/thread/useThreadPreview";
import { ThreadPreview } from "@/components/thread/ThreadPreview";
import { ClientProvider } from "@/providers/ClientProvider";
import { CirnoClient } from "@/lib/cirno-client";

const client = new CirnoClient({ url: "ws://127.0.0.1:1", reconnect: false });
client.requestMutation = async <T,>(action: string): Promise<T> => {
  if (action !== "temporary_chat.file_preview") throw new Error(`Unexpected fixture action: ${action}`);
  return { path: "/workspace/notes.txt", display_path: "notes.txt", project_path: "/workspace", language: "text",
    content: "Retained temporary file preview", size: 32, truncated: false, available: true, relative_path: "notes.txt" } as T;
};
function RetainedConversation({ active }: { active: boolean }) {
  const preview = useThreadPreview({ chatId: "private-preview", previewSessionKey: "websocket:private-preview",
    workspaceScope: null, temporary: true, headerActive: active, messageCount: 0 });
  return <section hidden={!active} aria-label="Temporary conversation">
    <button onClick={() => preview.openFilePreview("notes.txt")}>Open attached file</button>
    <section ref={preview.shellRef} className="relative flex min-h-[600px]">
      <div className="min-w-0 flex-1">Temporary conversation</div>
      <ThreadPreview controller={preview} />
    </section>
  </section>;
}
export function PreviewLifetimeFixture() {
  useTheme();
  const [active, setActive] = useState(true);
  return <ClientProvider client={client} token="fixture"><main className="p-4">
    <nav className="mb-4 flex gap-4"><button onClick={() => setActive(true)}>Temporary tab</button><button onClick={() => setActive(false)}>Other tab</button></nav>
    <RetainedConversation active={active} />
    {!active && <section>Another retained conversation</section>}
  </main></ClientProvider>;
}
