import { useEffect, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import { useLifetime } from "@/ui/resources/useLifetime";

type TerminalHost = { id: string; name: string };

export function useTerminalHosts(client: CirnoClient) {
  const [catalog, setCatalog] = useState({ client, nodes: [] as TerminalHost[], error: "" });
  const currentClient = useLifetime(client);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    void client.requestMutation<{ nodes: TerminalHost[] }>("instance.action", { action: "nodes.list" }).then(body => {
      if (current && currentClient()) setCatalog({ client, nodes: body.nodes, error: "" });
    }, reason => {
      if (current && currentClient()) setCatalog(previous => ({
        client, nodes: previous.client === client ? previous.nodes : [],
        error: reason instanceof Error ? reason.message : String(reason),
      }));
    });
    return () => { current = false; };
  }, [client, revision]);
  return {
    nodes: catalog.client === client ? catalog.nodes : [],
    error: catalog.client === client ? catalog.error : "",
    retry: () => { if (currentClient()) setRevision(value => value + 1); },
  };
}
