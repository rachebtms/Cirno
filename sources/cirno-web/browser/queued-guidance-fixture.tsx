import { useState, useEffect, useRef } from "react";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";

export function QueuedGuidanceFixture() {
  const [away, setAway] = useState(false);
  const blocked = useRef(true);
  const sendAttempts = useRef(0);
  const failStorage = new URLSearchParams(location.search).has("storageFailure");
  useEffect(() => {
    if (!failStorage) return;
    const write = Storage.prototype.setItem;
    Storage.prototype.setItem = function(key, value) {
      if (blocked.current && key === "cirno.webui.composerQueuedGuidance.v1:queued-fixture")
        throw new DOMException("Queue storage quota exceeded", "QuotaExceededError");
      write.call(this, key, value);
    };
    return () => { Storage.prototype.setItem = write; };
  }, [failStorage]);
  const [completed, setCompleted] = useState(new URLSearchParams(location.search).has("complete"));
  const [sent, setSent] = useState<Array<{ text: string; images?: SendAttachment[]; options?: SendOptions }>>([]);
  return <main className="mx-auto max-w-3xl p-4">
    <div className="mb-4 flex flex-wrap gap-4">
      {failStorage && <button onClick={() => { blocked.current = false; }}>Allow queue storage</button>}
      <button onClick={() => setAway(!away)}>Switch topic</button>
      <button onClick={() => setCompleted(true)}>Complete original reply</button>
    </div>
    {away ? <p>Another topic</p> : <ThreadComposer
      pendingQueueKey="queued-fixture"
      isStreaming={!completed}
      activeTurnId={completed ? null : "turn-a"}
      completedTurnIds={completed ? ["turn-a"] : []}
      onStop={() => setCompleted(true)}
      onSend={(text, images, options) => {
        if (new URLSearchParams(location.search).has("sendFailure") && sendAttempts.current++ === 0)
          return Promise.reject(new Error("Fixture upload unavailable"));
        setSent((current) => [...current, { text, images, options }]);
        return true;
      }}
    />}
    <output aria-label="Submitted messages">{JSON.stringify(sent)}</output>
  </main>;
}
