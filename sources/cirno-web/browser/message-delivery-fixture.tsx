import { useState } from "react";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { projectThreadEvents } from "@/lib/thread-event-projection";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";

export function MessageDeliveryFixture() {
  const [done, setDone] = useState(false);
  const frames: ThreadProjectionEvent[] = [
    { event: "user_message", chat_id: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: "hello", text: "你好", starts_turn: true },
    { event: "message", chat_id: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: "hello", kind: "tool_hint", text: "",
      tool_events: [{ call_id: "delivery", phase: "start", name: "user.message", arguments: { content: "你好呀 ❄ 我在这里。" } }] },
    { event: "message", chat_id: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: "hello", text: "你好呀 ❄ 我在这里。", render_as: "text" },
    ...(done ? [{ event: "message" as const, chat_id: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: "hello", kind: "tool_hint" as const, text: "",
      tool_events: [{ call_id: "delivery", phase: "end" as const, name: "user.message", arguments: { content: "你好呀 ❄ 我在这里。" }, result: "Message sent to websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" }] },
      { event: "turn_end" as const, chat_id: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: "hello" }] : []),
  ];
  return <main className="mx-auto max-w-4xl p-4">
    <button onClick={() => setDone(true)}>Complete delivery</button>
    <ThreadMessages messages={projectThreadEvents(frames)} isStreaming={!done} defaultActivityCollapsed={false} />
  </main>;
}
