import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  AutomationChat,
  AutomationChatsPayload,
  AutomationChatUpdate,
  SessionAutomationJob,
} from "@/lib/contracts/automations";

export type ChangeAutomationChat = (
  job: SessionAutomationJob,
  values: AutomationChatUpdate,
) => Promise<void>;
export type AutomationChatNames = ReadonlyMap<
  string,
  { title: string; handle: string }
>;
interface BindingDraft {
  target: AutomationChat;
  previous: AutomationChat;
  revision: string;
  message: string;
  editingMessage?: boolean;
}
export interface ChatBindingProps {
  job: SessionAutomationJob;
  data: AutomationChatsPayload | null;
  loadError: string | null;
  chatNames?: AutomationChatNames;
  showBrandLogos: boolean;
  onSave: ChangeAutomationChat;
  onSaved: (target: AutomationChat) => void;
  onReload: () => void;
  onBusyChange?: (busy: boolean) => void;
}
export function useChatBinding({
  job,
  data,
  loadError,
  chatNames,
  onSave,
  onSaved,
  onBusyChange,
}: ChatBindingProps) {
  const { t } = useTranslation();
  const tx = (key: string, values?: Record<string, string>) =>
    t(`settings.automations.chat.${key}`, values);
  const [draft, setDraft] = useState<BindingDraft | null>(null);
  const [saving, setSaving] = useState(false),
    [error, setError] = useState("");
  const [saved, setSaved] = useState<{
    target: AutomationChat;
    previous: AutomationChat;
  } | null>(null);
  const inFlight = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null),
    trigger = useRef<HTMLButtonElement>(null);
  const returning = useRef(false);
  const reviewing = !!draft;
  const locked = saving || !!job.state.pending;
  const pickerDisabled =
    locked ||
    !data?.chats.length ||
    !!loadError ||
    (!reviewing && data.revision !== job.chat_binding_revision);
  useEffect(() => {
    if (data)
      setSaved((previous) =>
        previous?.target.id === data.current?.id ? previous : null,
      );
  }, [data]);
  useEffect(() => {
    onBusyChange?.(saving);
    return () => onBusyChange?.(false);
  }, [onBusyChange, saving]);
  useEffect(() => {
    if (reviewing) heading.current?.focus();
  }, [reviewing]);
  useEffect(() => {
    if (!reviewing && !pickerDisabled && returning.current) {
      trigger.current?.focus();
      returning.current = false;
    }
  }, [reviewing, pickerDisabled]);
  const back = () => {
    returning.current = true;
    setDraft(null);
  };
  const current = data?.current;
  const fallback: AutomationChat = {
    id: "current",
    title: job.origin?.title || tx("current"),
    channel: job.origin?.channel || "websocket",
  };
  const baseTitle = (chat: AutomationChat) =>
    chatNames?.get(chat.id)?.title ?? chat.title;
  const counts = new Map<string, number>();
  for (const chat of data?.chats ?? []) {
    const title = baseTitle(chat);
    counts.set(title, (counts.get(title) ?? 0) + 1);
  }
  const chatTitle = (chat: AutomationChat) => {
    const title = baseTitle(chat),
      name = chatNames?.get(chat.id);
    return name && (counts.get(title) ?? 0) > 1
      ? `${title} · @${name.handle}`
      : title;
  };
  const targetUnavailable =
    !!draft &&
    !!data &&
    !data.chats.some(
      (chat) => chat.id === draft.target.id && !chat.unavailable,
    );
  const select = (id: string) => {
    const target = data?.chats.find((chat) => chat.id === id);
    if (!target || target.unavailable || id === current?.id) return;
    setError("");
    setDraft((previous) =>
      previous
        ? { ...previous, target }
        : {
            target,
            previous: current ?? fallback,
            revision: job.chat_binding_revision!,
            message: job.payload.message,
          },
    );
  };
  const save = async () => {
    if (
      !draft ||
      locked ||
      inFlight.current ||
      targetUnavailable ||
      !draft.message.trim()
    )
      return;
    inFlight.current = true;
    setSaving(true);
    setError("");
    try {
      await onSave(job, {
        target_id: draft.target.id,
        revision: draft.revision,
        message: draft.message,
      });
      onSaved(draft.target);
      setSaved({ target: draft.target, previous: draft.previous });
      back();
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : String(cause);
      const known: Record<string, string> = {
        automation_chat_conflict: "conflict",
        automation_chat_busy: "schedulerBusy",
        automation_chat_unavailable: "unavailable",
      };
      setError(known[reason] ? tx(known[reason]) : reason);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };
  return {
    tx,
    draft,
    setDraft,
    saved,
    current,
    fallback,
    saving,
    error,
    locked,
    pickerDisabled,
    targetUnavailable,
    chatTitle,
    heading,
    trigger,
    back,
    select,
    save,
  };
}
