import { useState } from "react";

import { AppearanceSettingsView } from "@/features/settings/overview/AppearanceSettingsView";
import { AutomationChatBindingView } from "@/features/automations/binding/AutomationChatBindingView";
import { AutomationRunDialogView, type AutomationRunResult } from "@/features/automations/runs/AutomationRunDialogView";
import { Button, Modal } from "@heroui/react";
import { DEFAULT_PREFERENCES } from "@/features/preferences/store";
import type { ThemePreference } from "@/hooks/useTheme";
import type { AutomationChatsPayload, SessionAutomationJob } from "@/lib/contracts/automations";
import { StatePicker, type ComponentExample } from "./example";
import { useGalleryTranslation } from "./i18n";

const job: SessionAutomationJob = {
  id: "gallery-report", name: "Weekly summary", enabled: true, chat_binding_revision: "gallery-1",
  schedule: { kind: "cron", expr: "30 9 * * 1", tz: "UTC" },
  payload: { message: "Summarize the changes and open questions." }, state: {},
  origin: { channel: "websocket", title: "Planning" },
};
const chats: AutomationChatsPayload = {
  revision: "gallery-1", current: { id: "planning", title: "Planning", channel: "websocket" },
  chats: [{ id: "planning", title: "Planning", channel: "websocket" },
    { id: "reviews", title: "Reviews", channel: "websocket" },
    { id: "archived", title: "Archived chat", channel: "websocket", unavailable: true }],
};

function RunResultPreview() {
  const { t, i18n } = useGalleryTranslation();
  const [mode, setMode] = useState<"complete" | "loading" | "error" | "empty" | "unavailable">("complete");
  const [open, setOpen] = useState(false);
  const result: AutomationRunResult = mode === "loading" || mode === "error"
    ? { status: mode, response: null }
    : { status: "loaded", response: mode === "empty" ? "" : mode === "unavailable" ? null : "## Weekly summary\n\n- **Completed:** component previews\n- **Next:** review the changes" };
  return <><StatePicker label={t("controls.runResult.state")} value={mode} options={["complete", "loading", "error", "empty", "unavailable"]} onChange={setMode} />
    <Button variant="secondary" onPress={() => setOpen(true)}>{t("controls.runResult.view")}</Button>
    <AutomationRunDialogView job={job} run={{ run_at_ms: Date.UTC(2026, 9, 12, 9, 30), status: "ok", duration_ms: 3200 }}
      locale={i18n.language} open={open} result={result} onRetry={() => setMode("complete")} onOpenChange={setOpen} /></>;
}

function ChatBindingPreview() {
  const { t } = useGalleryTranslation();
  const [mode, setMode] = useState<"ready" | "pending" | "load-error" | "conflict">("ready");
  const [task, setTask] = useState(job);
  const [data, setData] = useState(chats);
  const [targetTitle, setTargetTitle] = useState("");
  return <><StatePicker label={t("controls.chatBinding.state")} value={mode} options={["ready", "pending", "load-error", "conflict"]} onChange={setMode} />
    <Modal><Button variant="secondary">{t("controls.chatBinding.setChat")}</Button>
      <Modal.Backdrop><Modal.Container size="lg"><Modal.Dialog>
        <AutomationChatBindingView job={mode === "pending" ? { ...task, state: { pending: true } } : task}
          data={data} loadError={mode === "load-error" ? "Fixture chat list failed" : null} showBrandLogos={false} onReload={() => setMode("ready")}
          onSave={async (_task, values) => {
            if (mode === "conflict") throw new Error("automation_chat_conflict");
            setTask((current) => ({ ...current, chat_binding_revision: `${current.chat_binding_revision}-next`, payload: { ...current.payload, message: values.message } }));
          }} onSaved={(target) => {
            setData((current) => ({ ...current, current: target, revision: `${current.revision}-next` }));
            setTargetTitle(target.title);
          }}>{(picker) => <>
            <Modal.Header><Modal.Heading>{task.name}</Modal.Heading><Modal.CloseTrigger /></Modal.Header>
            <Modal.Body>{picker}</Modal.Body>
          </>}</AutomationChatBindingView>
      </Modal.Dialog></Modal.Container></Modal.Backdrop>
    </Modal><p role="status" className="mt-4 text-xs text-muted-foreground">{targetTitle ? t("controls.chatBinding.saved", { title: targetTitle }) : t("controls.chatBinding.hint")}</p></>;
}

function AppearancePreview() {
  const [theme, setTheme] = useState<ThemePreference>("system");
  const [preferences, setPreferences] = useState(DEFAULT_PREFERENCES);
  return <><AppearanceSettingsView themePreference={theme} onChangeTheme={setTheme}
    displayPreferences={preferences} onChangePreferences={setPreferences} />
    <pre role="status" className="mt-4 overflow-auto rounded-control bg-surface-secondary p-4 text-xs">{JSON.stringify({ theme, ...preferences }, null, 2)}</pre></>;
}


export const runtimeSettingsExamples: ComponentExample[] = [
  { title: "controls.runResult.title", files: ["sources/cirno-web/src/features/automations/runs/AutomationRunDialogView.tsx"], Preview: RunResultPreview,
    description: "controls.runResult.description",
    options: "controls.runResult.options",
    code: '<AutomationRunDialogView job={job} run={run} locale="zh-CN" open={open} result={{ status: "loaded", response }} onRetry={retry} onOpenChange={setOpen} />' },
  { title: "controls.chatBinding.title", files: ["sources/cirno-web/src/features/automations/binding/AutomationChatBindingView.tsx"], Preview: ChatBindingPreview,
    description: "controls.chatBinding.description",
    options: "controls.chatBinding.options",
    code: '<AutomationChatBindingView job={job} data={chats} loadError={null} showBrandLogos={false} onSave={save} onSaved={updateCurrent} onReload={reload}>{renderDetails}</AutomationChatBindingView>' },
  { title: "controls.appearance.title", files: ["sources/cirno-web/src/features/settings/overview/AppearanceSettingsView.tsx"], Preview: AppearancePreview,
    description: "controls.appearance.description",
    options: "controls.appearance.options",
    code: '<AppearanceSettingsView themePreference={preference} onChangeTheme={setTheme} displayPreferences={preferences} onChangePreferences={setPreferences} />' },
];