import { useCallback, useEffect, useRef, type Dispatch, type RefObject, type SetStateAction } from "react";
import type { ThreadTranscript } from "@/lib/thread-transcript";
import type { ThreadProjectionEvent, UIMessageTurnFields } from "@/lib/thread-event-projection";
import type { UIMessage } from "@/lib/contracts/messages";

type PendingStreamEvent =
  | { kind: "delta"; text: string; turn: UIMessageTurnFields; streamId?: string; source?: UIMessage["source"]; responseSources?: UIMessage["responseSources"] }
  | { kind: "reasoning"; text: string; turn: UIMessageTurnFields; streamId?: string };

const BACKGROUND_STREAM_FLUSH_INTERVAL_MS = 1_000;
// Markdown and layout work must leave room for input between visible updates.
const VISIBLE_STREAM_FLUSH_INTERVAL_MS = 50;
interface StreamBufferOptions {
  chatId: string | null;
  transcriptRef: RefObject<ThreadTranscript>;
  setMessages: Dispatch<SetStateAction<UIMessage[]>>;
  threadVisible: boolean;
  onForeground: () => void;
}

/** Own streamed-event batches, paint scheduling and hidden-pane refresh timing. */
export function useStreamBuffer({ chatId, transcriptRef, setMessages, threadVisible, onForeground }: StreamBufferOptions) {
  const threadVisibleRef = useRef(threadVisible);
  threadVisibleRef.current = threadVisible;
  const pendingStreamEventsRef = useRef<PendingStreamEvent[]>([]);
  const streamFrameRef = useRef<number | null>(null);
  const streamTimerRef = useRef<number | null>(null);
  const lastStreamFlushRef = useRef(0);


  const clearPendingStreamWork = useCallback(() => {
    if (streamFrameRef.current !== null) {
      window.cancelAnimationFrame(streamFrameRef.current);
      streamFrameRef.current = null;
    }
    if (streamTimerRef.current !== null) {
      window.clearTimeout(streamTimerRef.current);
      streamTimerRef.current = null;
    }
    pendingStreamEventsRef.current = [];
    lastStreamFlushRef.current = 0;
  }, []);

  const applyPendingStreamEvents = useCallback(
    (prev: UIMessage[], events: PendingStreamEvent[]): UIMessage[] => {
      transcriptRef.current.projection = { ...transcriptRef.current.projection, messages: prev };
      for (let index = 0; index < events.length; index++) {
        const event = events[index];
        const chunks = [event.text];
        const members = event.turn.turnSeq === undefined ? [] : [event.turn.turnSeq];
        let turn = event.turn;
        while (index + 1 < events.length) {
          const nextEvent = events[index + 1];
          if (nextEvent.kind !== event.kind
            || nextEvent.turn.turnId !== event.turn.turnId
            || nextEvent.turn.turnPhase !== event.turn.turnPhase
            || nextEvent.streamId !== event.streamId
            || (nextEvent.kind === "delta" && event.kind === "delta"
              && (nextEvent.source !== event.source
                || JSON.stringify(nextEvent.responseSources) !== JSON.stringify(event.responseSources)))) break;
          chunks.push(nextEvent.text);
          if (nextEvent.turn.turnSeq !== undefined) members.push(nextEvent.turn.turnSeq);
          turn = { ...turn, ...nextEvent.turn };
          index++;
        }
        const text = chunks.join("");
        const projectedEvent: ThreadProjectionEvent = event.kind === "delta"
          ? {
              event: "delta",
              chat_id: chatId ?? "",
              text,
              turn_id: turn.turnId,
              turn_phase: turn.turnPhase,
              turn_seq: turn.turnSeq,
              source: event.source,
              response_sources: event.responseSources,
            }
          : {
              event: "reasoning_delta",
              chat_id: chatId ?? "",
              text,
              turn_id: turn.turnId,
              turn_phase: turn.turnPhase,
              turn_seq: turn.turnSeq,
            };
        projectedEvent.stream_id = event.streamId;
        if (turn.turnId && members.length) {
          const ranges: Array<[number, number]> = [];
          for (const seq of members) {
            const last = ranges[ranges.length - 1];
            if (last && last[1] + 1 === seq) last[1] = seq;
            else ranges.push([seq, seq]);
          }
          projectedEvent.projection_receipts = [{ turn_id: turn.turnId, ranges }];
        }
        transcriptRef.current.project(projectedEvent, {
          createId: () => crypto.randomUUID(), now: Date.now(), startSeq: event.turn.turnSeq,
        });
      }
      return transcriptRef.current.messages;
    },
    [chatId, transcriptRef],
  );

  const flushPendingStreamEvents = useCallback((end?: Extract<ThreadProjectionEvent, { event: "stream_end" }>) => {
    lastStreamFlushRef.current = 0;
    if (streamFrameRef.current !== null) {
      window.cancelAnimationFrame(streamFrameRef.current);
      streamFrameRef.current = null;
    }
    if (streamTimerRef.current !== null) {
      window.clearTimeout(streamTimerRef.current);
      streamTimerRef.current = null;
    }
    const events = pendingStreamEventsRef.current;
    if (events.length === 0 && !end) return;
    pendingStreamEventsRef.current = [];
    setMessages((prev) => {
      const nextMessages = events.length > 0 ? applyPendingStreamEvents(prev, events) : prev;
      transcriptRef.current.projection = { ...transcriptRef.current.projection, messages: nextMessages };
      if (end) transcriptRef.current.project(end, {
        createId: () => crypto.randomUUID(), now: Date.now(),
      });
      return transcriptRef.current.messages;
    });
  }, [applyPendingStreamEvents, setMessages, transcriptRef]);

  const schedulePendingStreamFlush = useCallback(function schedule() {
    if (streamFrameRef.current !== null || streamTimerRef.current !== null) return;
    if (document.visibilityState === "hidden" || !threadVisibleRef.current) {
      streamTimerRef.current = window.setTimeout(() => {
        streamTimerRef.current = null;
        const events = pendingStreamEventsRef.current;
        if (events.length === 0) return;
        pendingStreamEventsRef.current = [];
        setMessages((prev) => applyPendingStreamEvents(prev, events));
      }, BACKGROUND_STREAM_FLUSH_INTERVAL_MS);
      return;
    }
    const delay = VISIBLE_STREAM_FLUSH_INTERVAL_MS
      - (performance.now() - lastStreamFlushRef.current);
    if (delay > 0) {
      streamTimerRef.current = window.setTimeout(() => {
        streamTimerRef.current = null;
        schedule();
      }, delay);
      return;
    }
    streamFrameRef.current = window.requestAnimationFrame(() => {
      streamFrameRef.current = null;
      const events = pendingStreamEventsRef.current;
      if (events.length === 0) return;
      pendingStreamEventsRef.current = [];
      lastStreamFlushRef.current = performance.now();
      setMessages((prev) => applyPendingStreamEvents(prev, events));
    });
  }, [applyPendingStreamEvents, setMessages, transcriptRef]);

  useEffect(() => {
    if (threadVisible) {
      flushPendingStreamEvents();
    } else if (streamFrameRef.current !== null || streamTimerRef.current !== null) {
      if (streamFrameRef.current !== null) window.cancelAnimationFrame(streamFrameRef.current);
      streamFrameRef.current = null;
      if (streamTimerRef.current !== null) window.clearTimeout(streamTimerRef.current);
      streamTimerRef.current = null;
      schedulePendingStreamFlush();
    }
  }, [threadVisible, flushPendingStreamEvents, schedulePendingStreamFlush]);

  useEffect(() => {
    let hidden = document.visibilityState === "hidden";
    const onVisibilityChange = () => {
      const wasHidden = hidden;
      hidden = document.visibilityState === "hidden";
      if (wasHidden && !hidden && threadVisibleRef.current) onForeground();
      if (pendingStreamEventsRef.current.length === 0) return;
      if (document.visibilityState === "visible" && threadVisibleRef.current) {
        flushPendingStreamEvents();
      } else {
        if (streamFrameRef.current !== null) window.cancelAnimationFrame(streamFrameRef.current);
        streamFrameRef.current = null;
        if (streamTimerRef.current !== null) window.clearTimeout(streamTimerRef.current);
        streamTimerRef.current = null;
        schedulePendingStreamFlush();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [flushPendingStreamEvents, schedulePendingStreamFlush, onForeground]);

  const enqueue = useCallback((event: PendingStreamEvent) => {
    pendingStreamEventsRef.current.push(event);
    schedulePendingStreamFlush();
  }, [schedulePendingStreamFlush]);
  const discardTurn = useCallback((turnId: string) => {
    pendingStreamEventsRef.current = pendingStreamEventsRef.current.filter(event => event.turn.turnId !== turnId);
  }, []);
  const snapshot = useCallback((messages: UIMessage[]) => pendingStreamEventsRef.current.length > 0
    ? applyPendingStreamEvents(messages, pendingStreamEventsRef.current) : messages, [applyPendingStreamEvents]);

  return { enqueue, discardTurn, snapshot, flush: flushPendingStreamEvents, clear: clearPendingStreamWork };
}
