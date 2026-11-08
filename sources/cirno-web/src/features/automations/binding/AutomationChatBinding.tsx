import { useEffect, useState, type ReactNode } from "react";

import {
  AutomationChatBindingView,
  type AutomationChatNames,
  type ChangeAutomationChat,
} from "./AutomationChatBindingView";
import { fetchAutomationChats } from "@/lib/api";
import { readPreferences } from "@/features/preferences/store";
import type {
  AutomationChatsPayload,
  SessionAutomationJob,
} from "@/lib/contracts/automations";

export type {
  AutomationChatNames,
  ChangeAutomationChat,
} from "./AutomationChatBindingView";

export function AutomationChatBinding({
  job,
  token,
  chatNames,
  onSave,
  children,
  onBusyChange,
}: {
  job: SessionAutomationJob;
  token: string;
  onSave: ChangeAutomationChat;
  chatNames?: AutomationChatNames;
  children: (picker: ReactNode) => ReactNode;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [data, setData] = useState<AutomationChatsPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    void fetchAutomationChats(token, job.id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setLoadError(
            reason instanceof Error ? reason.message : String(reason),
          );
      });
    return () => controller.abort();
  }, [token, job.id, job.chat_binding_revision, reload]);
  return (
    <AutomationChatBindingView
      job={job}
      data={data}
      loadError={loadError}
      chatNames={chatNames}
      showBrandLogos={readPreferences().brandLogos}
      onSave={onSave}
      onBusyChange={onBusyChange}
      onReload={() => setReload((value) => value + 1)}
      onSaved={(target) => {
        setData((previous) =>
          previous ? { ...previous, current: target } : previous,
        );
        setReload((value) => value + 1);
      }}
    >
      {children}
    </AutomationChatBindingView>
  );
}
