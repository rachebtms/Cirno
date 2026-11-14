import { useState } from "react";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { useTheme } from "@/hooks/useTheme";
import type { UIMessage } from "@/lib/contracts/messages";

export function RouterActivityFixture() {
  useTheme();
  const [base] = useState(() => Date.now() - 7_200_000);
  const [phase, setPhase] = useState<"idle" | "running" | "done">("idle");
  const [startedAt, setStartedAt] = useState(0);
  const heartbeat = (id: string, start: number): UIMessage => ({
    id, turnId: id, role: "user", content: `Inspect authorized tasks (${id}).`, createdAt: start,
    inputOrigin: { kind: "heartbeat", label: "Heartbeat" },
  });
  const messages: UIMessage[] = [
    { id: "owner", role: "user", content: "Keep an eye on the experiments.", createdAt: base - 1000 },
    heartbeat("first", base),
    { id: "first-result", role: "assistant", activityKind: "model", content: "First inspection complete.",
      createdAt: base + 5000, turnId: "first", latencyMs: 5000 },
    heartbeat("second", base + 3_600_000),
    { id: "second-result", role: "assistant", activityKind: "model", content: "Second inspection complete.",
      createdAt: base + 3_607_000, turnId: "second", latencyMs: 7000 },
  ];
  if (phase !== "idle") messages.push(heartbeat("current", startedAt));
  if (phase === "done") messages.push({ id: "current-result", role: "assistant", content: "", reasoning: "Current inspection complete.",
    createdAt: startedAt + 3000, turnId: "current", latencyMs: 3000 });
  return <main className="mx-auto max-w-3xl space-y-4 p-4 sm:p-8">
    <h1 className="text-xl font-semibold">Router activity</h1>
    <div className="flex gap-4">
      <button onClick={() => { setStartedAt(Date.now()); setPhase("running"); }}>Start heartbeat</button>
      <button onClick={() => setPhase("done")} disabled={phase !== "running"}>Finish heartbeat</button>
    </div>
    <section aria-label="Router conversation">
      <ThreadMessages activityGrouping="conversation" assistantBubbles defaultActivityCollapsed messages={messages}
        isStreaming={phase === "running"} activeTurnId={phase === "running" ? "current" : null} />
    </section>
  </main>;
}
