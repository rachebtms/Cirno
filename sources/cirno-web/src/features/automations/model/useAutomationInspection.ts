import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { displayTitle } from "@/lib/chat-groups";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { AutomationChatNames } from "../binding/AutomationChatBinding";
import type { AutomationsPageProps } from "./contracts";

export function useAutomationInspection({
  payload,
  titleOverrides,
  sessions,
  returnToDetailJob,
  onReturnToDetailHandled,
}: AutomationsPageProps) {
  const { t } = useTranslation();
  const [inspected, setInspected] = useState<SessionAutomationJob | null>(null);
  const [open, setOpen] = useState(false);
  const jobs = useMemo(
    () =>
      (payload?.jobs ?? []).map((job) => {
        const origin = job.origin;
        if (origin?.channel !== "websocket") return job;
        const title = displayTitle(
          {
            key: origin.session_key ?? "",
            title: origin.title,
            preview: origin.preview ?? "",
          },
          titleOverrides ?? {},
          t("chat.newChat"),
        );
        return title === origin.title
          ? job
          : { ...job, origin: { ...origin, title } };
      }),
    [payload, titleOverrides, t],
  );
  const chatNames: AutomationChatNames = useMemo(
    () =>
      new Map(
        (sessions ?? []).flatMap((session) =>
          session.handle
            ? [
                [
                  session.handle.id,
                  {
                    title: displayTitle(
                      session,
                      titleOverrides ?? {},
                      t("chat.newChat"),
                    ),
                    handle: session.handle.name,
                  },
                ] as const,
              ]
            : [],
        ),
      ),
    [sessions, titleOverrides, t],
  );
  const live = jobs.find((job) => job.id === inspected?.id);
  useEffect(() => {
    if (live) setInspected(live);
    else setOpen(false);
  }, [live]);
  useEffect(() => {
    if (!returnToDetailJob) return;
    setInspected(
      jobs.find((job) => job.id === returnToDetailJob.id) ?? returnToDetailJob,
    );
    setOpen(true);
    onReturnToDetailHandled?.();
  }, [jobs, onReturnToDetailHandled, returnToDetailJob]);
  return {
    jobs,
    chatNames,
    selected: live ?? inspected,
    open,
    setOpen,
    inspect: (job: SessionAutomationJob) => {
      setInspected(job);
      setOpen(true);
    },
    handOff: (
      callback: (job: SessionAutomationJob) => void,
      job: SessionAutomationJob,
    ) => {
      setOpen(false);
      callback(job);
    },
  };
}
