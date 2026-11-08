import { useCallback, useMemo, useState } from "react";
import { useClient } from "@/providers/ClientProvider";
import { useMutation } from "@/ui/resources/useMutation";
import { hasToolHistory } from "@/lib/thread-inputs";
import type { UIMessage } from "@/lib/contracts/messages";
import { InlineMessageEditor } from "../InlineMessageEditor";

interface MessageEditingOptions {
  sessionKey: string | null;
  displayMessages: UIMessage[];
  turnActive: boolean;
  resetHistory: (turnId?: string) => void;
}

export function useMessageEditing({
  sessionKey,
  displayMessages,
  turnActive,
  resetHistory,
}: MessageEditingOptions) {
  const { client } = useClient(),
    owner = useMemo(() => ({ client, sessionKey }), [client, sessionKey]);
  const mutation = useMutation(owner);
  const [draft, setDraft] = useState<{
    owner: object;
    message: UIMessage;
    text: string;
  } | null>(null);
  const current = draft?.owner === owner ? draft : null;
  const beginMessageEdit = useCallback(
    (message: UIMessage) => {
      if (!sessionKey) return;
      mutation.clear();
      setDraft({ owner, message, text: message.content });
    },
    [sessionKey, owner, mutation.clear],
  );
  const hasEffects = useMemo(() => {
    if (!current) return false;
    const index = displayMessages.findIndex(
      (message) => message.id === current.message.id,
    );
    return displayMessages.slice(index + 1).some(hasToolHistory);
  }, [current, displayMessages]);
  const submit = () => {
    if (
      !sessionKey ||
      !current?.message.turnId ||
      !current.text.trim() ||
      turnActive
    )
      return;
    void mutation.run(
      () =>
        client.requestMutation<{ turn_id: string }>("instance.action", {
          action: "conversations.edit",
          values: {
            session_key: sessionKey,
            turn_id: current.message.turnId,
            content: current.text,
          },
        }),
      (result) => {
        setDraft(null);
        resetHistory(result.turn_id);
      },
    );
  };
  return {
    beginMessageEdit,
    editBusy: mutation.busy,
    messageEditor: current
      ? {
          messageId: current.message.id,
          content: (
            <InlineMessageEditor
              value={current.text}
              busy={mutation.busy || turnActive}
              error={mutation.error ?? ""}
              hasToolEffects={hasEffects}
              onChange={(text) =>
                setDraft((previous) =>
                  previous?.owner === owner ? { ...previous, text } : previous,
                )
              }
              onCancel={() => setDraft(null)}
              onSubmit={submit}
            />
          ),
        }
      : undefined,
  };
}
