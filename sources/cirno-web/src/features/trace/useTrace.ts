import { useCallback, useEffect, useRef, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { RecordingInfo, TraceDetail, TraceEvent, TracePage } from "./contracts";

const errorText = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);

export function useTrace(client: CirnoClient, recordingId: string, active: boolean,
  onCloseReady: (close: () => Promise<void>) => void) {
  const [page, setPage] = useState<TracePage | null>(null);
  const [info, setInfo] = useState<RecordingInfo | null>(null);
  const [cursors, setCursors] = useState<(number | null)[]>([null]);
  const [kind, setKind] = useState("all");
  const [source, setSource] = useState("");
  const cursor = cursors[cursors.length - 1];
  const [selected, setSelected] = useState<TraceEvent | null>(null);
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [detailBusy, setDetailBusy] = useState(false);
  const [revision, refresh] = useState(0);
  const listEpoch = useRef(0), detailEpoch = useRef(0), inFlight = useRef<number | null>(null);
  const closing = useRef(false);
  const creations = useRef(new Set<Promise<RecordingInfo>>());
  const action = useCallback(<T,>(operation: string, values: object = {}) => client.requestMutation<T>("workbench.action", {
    action: `trace.${operation}`, values: { recording_id: recordingId, ...values },
  }), [client, recordingId]);
  const create = useCallback(() => {
    const pending = action<RecordingInfo>("create");
    creations.current.add(pending);
    const settled = () => { creations.current.delete(pending); };
    void pending.then(settled, settled);
    return pending;
  }, [action]);
  useEffect(() => {
    let disposed = false; closing.current = false;
    const opening = create();
    onCloseReady(async () => {
      closing.current = true;
      try {
        // Creation errors are displayed below; a failed tab must still be closable.
        await Promise.allSettled([...creations.current]);
        await action("close");
      } catch (reason) { closing.current = false; throw reason; }
    });
    void opening.then((body) => { if (!disposed) setInfo(body); }).catch((reason) => { if (!disposed) setError(errorText(reason)); });
    return () => { disposed = true; listEpoch.current++; detailEpoch.current++; };
  }, [action, create, onCloseReady]);
  const ready = info !== null;
  const load = useCallback(async () => {
    if (!ready || closing.current || inFlight.current === listEpoch.current) return;
    const stamp = ++listEpoch.current; inFlight.current = stamp; setBusy(true);
    try {
      const body = await action<TracePage>("events", { before: cursor, kind: kind === "all" ? null : kind, session_key: source || null });
      if (stamp !== listEpoch.current) return;
      setPage(body); setInfo(body); setError("");
    } catch (reason) { if (stamp === listEpoch.current) setError(errorText(reason)); }
    finally { if (stamp === listEpoch.current) setBusy(false); if (inFlight.current === stamp) inFlight.current = null; }
  }, [ready, action, cursor, kind, source, revision]);
  useEffect(() => { void load(); return () => { listEpoch.current++; }; }, [load]);
  useEffect(() => {
    if (!active || cursor !== null) return;
    const poll = () => { if (document.visibilityState !== "hidden") void load(); };
    const timer = window.setInterval(poll, 2000);
    document.addEventListener("visibilitychange", poll);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", poll); };
  }, [load, active, cursor]);
  const inspect = useCallback(async (offset = 0) => {
    if (!selected || !info || closing.current) return;
    const stamp = ++detailEpoch.current; setDetailBusy(true);
    try {
      const body = await action<TraceDetail>("detail", { event_id: selected.id, epoch: info.epoch, offset });
      if (stamp !== detailEpoch.current) return;
      setDetail((old) => offset && old ? { ...old, messages: [...(old.messages ?? []), ...(body.messages ?? [])] } : body);
    } catch (reason) { if (stamp === detailEpoch.current) setError(errorText(reason)); }
    finally { if (stamp === detailEpoch.current) setDetailBusy(false); }
  }, [action, selected, info?.epoch]);
  const status = page?.events.find((event) => event.id === selected?.id)?.status;
  useEffect(() => { setDetail(null); void inspect(); return () => { detailEpoch.current++; }; }, [inspect, status]);
  const control = async (operation: "start" | "pause" | "clear") => {
    listEpoch.current++; setBusy(true);
    if (operation === "clear") { detailEpoch.current++; setSelected(null); setDetail(null); }
    try {
      const body = await action<RecordingInfo>(operation);
      listEpoch.current++; setInfo(body);
      if (operation === "clear") {
        detailEpoch.current++; setSelected(null); setDetail(null); setDetailBusy(false);
        setPage(null); setCursors([null]);
      }
      refresh((old) => old + 1); setError("");
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  };
  const reconnect = async () => {
    if (closing.current) return;
    listEpoch.current++; setBusy(true);
    try {
      const body = await create();
      if (closing.current) return;
      listEpoch.current++;
      if (body.epoch !== info?.epoch) {
        detailEpoch.current++; setSelected(null); setDetail(null); setDetailBusy(false);
        setPage(null); setCursors([null]);
      }
      setInfo(body); setError(""); refresh((old) => old + 1);
      if (body.epoch === info?.epoch) void inspect();
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  };
  return { page, info, selected, setSelected, detail, error, busy, detailBusy, kind, source,
    setKind: (value: string) => { setCursors([null]); setKind(value); },
    setSource: (value: string) => { setCursors([null]); setSource(value); },
    refresh: () => void reconnect(), control,
    moreDetail: () => void inspect(detail?.messages?.length ?? 0),
    older: () => { if (page?.before) setCursors((old) => [...old, page.before]); },
    newer: () => setCursors((old) => old.slice(0, -1)), newest: () => setCursors([null]), canNewer: cursors.length > 1,
  };
}
