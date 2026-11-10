import type { WebUIMutationTransport } from "@/lib/api";
import { MemoryLibrary } from "./MemoryLibrary";
import "./memory-tab.css";

export function MemoryTab({ client, active }: { client: WebUIMutationTransport; active: boolean }) {
  return <div className="memory-screen"><MemoryLibrary client={client} graph active={active} /></div>;
}
