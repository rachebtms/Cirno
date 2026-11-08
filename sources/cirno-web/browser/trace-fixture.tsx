import { useCallback, useMemo, useRef, useState } from "react";
import { useTheme } from "@/hooks/useTheme";
import { TraceTab } from "@/features/trace/TraceTab";
import type { CirnoClient } from "@/lib/cirno-client";
import type { RecordingInfo, TraceEvent } from "@/features/trace/contracts";

const initialEvents: TraceEvent[] = Array.from({ length: 25 }, (_, id) => ({
  id: id + 1, kind: ["input", "tool_activity", "request", "compaction", "reasoning_delta"][id % 5],
  created_ms: 1794000000000 + id * 120, summary: ["Research question", "nodes.execute • nvidia-smi", "Model request", "Context checkpoint", "Inspecting experiment state"][id % 5],
  status: "completed", session_key: id % 2 ? "websocket:worker" : "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: `turn-${id}`, bytes: 128 + id,
}));
export function TraceFixture() {
  useTheme();
  const [closed, setClosed] = useState(false);
  const [actions, setActions] = useState<unknown[]>([]);
  const closing = useRef<() => Promise<void>>(async () => {});
  const ready = useCallback((close: () => Promise<void>) => { closing.current = close; }, []);
  const client = useMemo(() => {
    let info: RecordingInfo = { id: "fixture-recording", epoch: "first", running: true, reason: null, count: initialEvents.length, created_ms: 1794000000000 };
    const delayedEmpty = new URLSearchParams(location.search).has("emptyPolling");
    let events = delayedEmpty ? [] : initialEvents;
    let reads = 0;
    return { exportTraceRecording: async () => new Blob([new Uint8Array([80, 75, 5, 6, ...Array(18).fill(0)])], { type: "application/zip" }), requestMutation: async (_name: string, payload: { action: string; values: Record<string, unknown> }) => {
      setActions(old => [...old, payload]);
      const { action, values } = payload;
      if (action === "trace.close") { setClosed(true); return { ok: true }; }
      if (action === "trace.clear") { events = []; info = { ...info, epoch: "cleared", count: 0 }; }
      if (action === "trace.start" || action === "trace.pause") info = { ...info, running: action === "trace.start" };
      if (action === "trace.events" && delayedEmpty && ++reads > 1) await new Promise(resolve => setTimeout(resolve, 350));
      if (action === "trace.events") return { ...info, events: events.filter(event => (!values.kind || values.kind === "tool" && event.kind === "tool_activity" || event.kind === values.kind)
        && (!values.session_key || event.session_key === values.session_key)), before: null, sources: ["websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "websocket:worker"] };
      if (action === "trace.detail") return { event: { name: "nodes.execute", command: "nvidia-smi", node: "research-gpu" },
        messages: [{ role: "system", content: "Shared model instructions" }, { role: "user", content: "Inspect the GPU before starting a job" }], total: 2,
        tools: [{ name: "nodes.execute" }], response: { status: "completed", text: "GPU available" } };
      return info;
    } } as unknown as CirnoClient;
  }, []);
  if (closed) return <h1>Recording closed</h1>;
  return <main style={{ display: "flex", flexDirection: "column", height: "100dvh", minWidth: 0 }}>
    <TraceTab client={client} recordingId="fixture-recording" active onCloseReady={ready} />
    <button style={{ flexShrink: 0 }} onClick={() => void closing.current()}>Close recording tab</button>
    <output hidden aria-label="Trace actions">{JSON.stringify(actions)}</output>
  </main>;
}
