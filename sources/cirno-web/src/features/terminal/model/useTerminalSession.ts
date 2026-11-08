import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import { createTerminalRenderer, terminalPalette } from "./renderer";

export type TerminalPhase = "idle" | "connecting" | "connected" | "failed" | "exited";
type Operation = "create" | "read" | "write" | "resize" | "close";
interface TerminalOutput { data: string; cursor: number; reset: boolean; exit_code: number | null }
export function useTerminalSession({ client, terminalKey, cwd, nodeId, active, onCloseReady, paletteRevision, exitedText }: {
  client: CirnoClient; terminalKey: string; cwd?: string; nodeId: string; active: boolean;
  onCloseReady: (close: () => Promise<void>) => void; paletteRevision: unknown; exitedText: (code: number) => string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const renderer = useRef<ReturnType<typeof createTerminalRenderer> | null>(null);
  const closeRef = useRef<(() => Promise<void>) | null>(null);
  const activeRef = useRef(active); activeRef.current = active;
  const exitLabel = useRef(exitedText); exitLabel.current = exitedText;
  const [attempt, setAttempt] = useState(0);
  const [phase, setPhase] = useState<TerminalPhase>("idle");
  const [errors, setErrors] = useState<Partial<Record<Operation, string>>>({});
  const connecting = useRef(false);
  const report = (operation: Operation, reason?: unknown) => setErrors(old => {
    const next = { ...old };
    if (reason === undefined) delete next[operation];
    else next[operation] = reason instanceof Error ? reason.message : String(reason);
    return next;
  });
  async function connect() {
    if (connecting.current || phase === "connecting" || phase === "connected") return;
    connecting.current = true; setPhase("connecting");
    try { await closeRef.current?.(); setErrors({}); setAttempt(value => value + 1); }
    catch (reason) { report("close", reason); setPhase("failed"); }
    finally { connecting.current = false; }
  }
  useLayoutEffect(() => {
    if (renderer.current && host.current) renderer.current.terminal.options.theme = terminalPalette(host.current);
  }, [paletteRevision]);
  useEffect(() => {
    if (!attempt || !host.current) return;
    let disposed = false, closing = false, reading = false;
    let identifier: string | null = null, cursor = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = createTerminalRenderer(host.current); renderer.current = current;
    const { terminal, fit } = current;
    const action = <T,>(operation: Operation, values: object) => client.requestMutation<T>("workbench.action", { action: `terminal.${operation}`, values });
    let writes = Promise.resolve();
    const opening = action<{ id: string }>("create", { key: terminalKey, cwd, node_id: nodeId === "local" ? null : nodeId, cols: terminal.cols, rows: terminal.rows });
    let closeRequest: Promise<void> | null = null;
    const close = (): Promise<void> => {
      if (closeRequest) return closeRequest;
      closing = true; terminal.options.disableStdin = true;
      closeRequest = (async () => {
        await Promise.allSettled([opening, writes]);
        await action("close", { id: identifier ?? terminalKey });
        if (!disposed) report("close");
        identifier = null;
      })().catch(reason => {
        closeRequest = null; closing = false;
        if (!disposed) {
          report("close", reason);
          terminal.options.disableStdin = !identifier;
          setPhase(identifier ? "connected" : "failed");
          clearTimeout(timer); void poll();
        }
        throw reason;
      });
      return closeRequest;
    };
    closeRef.current = close; onCloseReady(close);
    const input = terminal.onData(data => {
      if (closing || !identifier) return;
      writes = writes.then(async () => {
        if (!disposed && !closing && identifier) { await action("write", { id: identifier, data }); report("write"); }
      }).catch(reason => { if (!disposed) report("write", reason); });
    });
    const resize = () => {
      if (identifier && !closing) void action("resize", { id: identifier, cols: terminal.cols, rows: terminal.rows })
        .then(() => { if (!disposed) report("resize"); }, reason => { if (!disposed) report("resize", reason); });
    };
    const size = terminal.onResize(resize);
    const observer = new ResizeObserver(() => { if (activeRef.current) fit.fit(); });
    observer.observe(host.current);
    const poll = async () => {
      if (disposed || closing || reading || !identifier) return;
      if (document.visibilityState !== "hidden") {
        reading = true;
        try {
          const body = await action<TerminalOutput>("read", { id: identifier, cursor });
          if (disposed || closing) return;
          if (body.reset) terminal.reset();
          if (body.data) terminal.write(body.data);
          cursor = body.cursor; report("read");
          if (body.exit_code !== null) {
            terminal.options.disableStdin = true; setPhase("exited");
            terminal.writeln(`\r\n[${exitLabel.current(body.exit_code)}]`); return;
          }
        } catch (reason) { if (!disposed && !closing) report("read", reason); }
        finally { reading = false; }
      }
      if (!disposed && !closing) timer = setTimeout(() => void poll(), activeRef.current ? 250 : 1500);
    };
    const wake = () => {
      if (document.visibilityState !== "hidden" && !disposed && !closing) { clearTimeout(timer); fit.fit(); void poll(); }
    };
    document.addEventListener("visibilitychange", wake);
    void opening.then(body => {
      identifier = body.id;
      if (disposed || closing) return;
      terminal.options.disableStdin = false; setPhase("connected");
      fit.fit(); resize(); if (activeRef.current) terminal.focus();
      void poll();
    }, reason => { if (!disposed && !closing) { report("create", reason); setPhase("failed"); } });
    return () => {
      disposed = true; clearTimeout(timer); document.removeEventListener("visibilitychange", wake);
      input.dispose(); size.dispose(); observer.disconnect(); terminal.dispose();
      if (renderer.current === current) renderer.current = null;
      void close().catch(reason => console.error("Terminal cleanup failed", reason));
    };
  }, [client, cwd, terminalKey, nodeId, onCloseReady, attempt]);
  return { host, phase, started: attempt > 0, errors: [...new Set(Object.values(errors))], connect };
}
