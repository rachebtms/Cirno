import { useEffect, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";

export function useTerminalHosts(client: CirnoClient) {
  const [nodes, setNodes] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    void client.requestMutation<{ nodes: typeof nodes }>("instance.action", { action: "nodes.list" }).then(body => {
      if (current) { setNodes(body.nodes); setError(""); }
    }, reason => { if (current) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { current = false; };
  }, [client, revision]);
  return { nodes, error, retry: () => setRevision(value => value + 1) };
}
