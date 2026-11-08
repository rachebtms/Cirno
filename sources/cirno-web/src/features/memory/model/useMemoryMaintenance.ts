import { useEffect, useRef, useState } from "react";
import type { MemoryService } from "./service";
interface Maintenance {
  service: MemoryService;
  phase: "idle" | "running" | "complete" | "stopped" | "error";
  scanned: number;
  action: "reindex" | "retry" | null;
  error: string | null;
}
interface Run {
  service: MemoryService;
  stop: boolean;
}
export function useMemoryMaintenance(service: MemoryService, onChanged: () => Promise<unknown>) {
  const flight = useRef<Run | null>(null);
  const [state, setState] = useState<Maintenance>({
    service,
    phase: "idle",
    scanned: 0,
    action: null,
    error: null,
  });
  useEffect(
    () => () => {
      if (flight.current?.service === service) flight.current = null;
    },
    [service],
  );
  const run = async (action: "reindex" | "retry") => {
    if (flight.current?.service === service) return;
    const operation = { service, stop: false };
    flight.current = operation;
    setState({ service, phase: "running", scanned: 0, action, error: null });
    let scanned = 0;
    try {
      let phase: Maintenance["phase"] = "idle";
      if (action === "reindex") {
        let more = true;
        while (more && !operation.stop && flight.current === operation) {
          const page = await service.reindex();
          if (flight.current !== operation) return;
          scanned += page.scanned;
          more = page.has_more;
          setState({ service, phase: "running", scanned, action, error: null });
        }
        phase = more ? "stopped" : "complete";
      } else await service.retry();
      if (flight.current !== operation) return;
      await onChanged();
      if (flight.current === operation) setState({ service, phase, scanned, action, error: null });
    } catch (reason) {
      if (flight.current === operation)
        setState({
          service,
          phase: "error",
          scanned,
          action,
          error: reason instanceof Error ? reason.message : String(reason),
        });
    } finally {
      if (flight.current === operation) flight.current = null;
    }
  };
  const current =
    state.service === service
      ? state
      : { service, phase: "idle" as const, scanned: 0, action: null, error: null };
  return {
    ...current,
    busy: current.phase === "running",
    run,
    stop: () => {
      if (flight.current) flight.current.stop = true;
    },
  };
}
