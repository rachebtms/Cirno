import { useRef, useState } from "react";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ComposerDraftStore } from "@/lib/composer-draft";
import { useTheme } from "@/hooks/useTheme";
import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";

let recoverStorage = () => {};
export function installDraftPersistenceFailure(parameters: URLSearchParams) {
  let blocked = true;
  recoverStorage = () => { blocked = false; };
  const failure = parameters.get("failure");
  const methods = { read: "getItem", save: "setItem", remove: "removeItem" } as const;
  const method = methods[failure as keyof typeof methods];
  if (!method) return;
  const original = Reflect.get(Storage.prototype, method);
  Reflect.set(Storage.prototype, method, function(this: Storage, key: string, ...values: string[]) {
    if (blocked && key === "cirno.composer-draft.v1.websocket:draft-a") throw new Error(`Draft ${failure} unavailable`);
    return Reflect.apply(original, this, [key, ...values]);
  });
}
export function DraftPersistenceFixture() {
  useTheme();
  const [store] = useState(() => new ComposerDraftStore());
  const [topic, setTopic] = useState("a");
  const [quotes, setQuotes] = useState<Record<string, string | null>>({});
  const [sent, setSent] = useState<Array<{ text: string; attachments?: SendAttachment[]; options?: SendOptions }>>([]);
  const pending = useRef<(() => void) | null>(null);
  const key = `websocket:draft-${topic}`;
  const quote = Object.hasOwn(quotes, topic) ? quotes[topic] : store.get(key, true)?.quotedContext ?? null;
  return <main className="mx-auto max-w-3xl p-4">
    <nav className="mb-4 flex flex-wrap gap-4">
      <button onClick={() => setTopic(current => current === "a" ? "b" : "a")}>Switch conversation</button>
      <button onClick={() => recoverStorage()}>Allow draft storage</button>
      <button onClick={() => pending.current?.()}>Accept pending send</button>
    </nav>
    <p className="mb-3">Conversation {topic}</p>
    <ThreadComposer key={key} draftKey={key} draftStore={store} persistDraft quotedContext={quote}
      onQuotedContextChange={text => setQuotes(current => ({ ...current, [topic]: text }))}
      onSend={(text, attachments, options) => {
        const accept = () => { setSent(current => [...current, { text, attachments, options }]); return true; };
        if (new URLSearchParams(location.search).has("delayed")) return new Promise<boolean>(resolve => { pending.current = () => resolve(accept()); });
        return accept();
      }} />
    <output aria-label="Submitted messages">{JSON.stringify(sent)}</output>
  </main>;
}
