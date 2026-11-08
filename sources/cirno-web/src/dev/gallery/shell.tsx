import { useState, type ReactNode } from "react";
import { Trans } from "react-i18next";

import { CapabilityMentionToken } from "@/components/CliAppMentionText";
import type { CapabilityMentionSegment } from "@/lib/composer-mention-text";
import { DeleteConfirm } from "@/components/DeleteConfirm";
import { FileActions } from "@/components/FileActions";
import { InlineTokenHighlight, INLINE_TOKEN_HIGHLIGHT_COLOR } from "@/components/InlineTokenHighlight";
import { SessionHandleLabel } from "@/components/SessionHandleLabel";
import { SlashCommandText } from "@/components/SlashCommandText";
import { StartupShell } from "@/components/StartupShell";
import { UserMessageText } from "@/components/UserMessageText";
import * as ProductIcons from "@/components/icons/product-icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { SessionMention } from "@/lib/contracts/messages";
import { cn } from "@/lib/utils";
import { Sample, StatePicker, type ComponentExample } from "./example";
import { useGalleryTranslation } from "./i18n";

const cliApp: CliAppInfo = {
  name: "cirno", display_name: "Cirno", category: "assistant", description: "Local assistant",
  requires: "Python", source: "local", entry_point: "cirno", install_supported: true,
  installed: true, available: true, status: "installed", skill_installed: true,
  logo_url: "/brand/cirno_snowflake_icon_512.png", brand_color: "var(--inline-token-highlight)",
};
const mcpPreset: McpPresetInfo = {
  name: "files", display_name: "Workspace files", category: "files", description: "Workspace files",
  docs_url: "", transport: "stdio", requires: "", note: "", install_supported: true,
  installed: true, configured: true, available: true, status: "configured", required_fields: [],
  connection_summary: "Local files",
};
const sessionMention: SessionMention = {
  id: "gallery-session", name: "design", session_key: "webui:gallery-design", title: "组件设计",
};

const automations: SessionAutomationJob[] = [
  { id: "gallery-daily", name: "每日项目摘要", enabled: true, schedule: { kind: "cron", expr: "0 9 * * *", tz: "Asia/Shanghai" }, payload: { message: "Summarize project updates" }, state: { next_run_at_ms: Date.UTC(2026, 9, 14, 1) } },
  { id: "gallery-hourly", name: "每小时检查", enabled: false, schedule: { kind: "every", every_ms: 3_600_000 }, payload: { message: "Check updates" }, state: {} },
  { id: "gallery-trigger", name: "发布后检查", enabled: true, schedule: { kind: "local" }, payload: { message: "Check the release", kind: "local_trigger" }, state: {} },
  { id: "gallery-once", name: "一次性提醒", enabled: true, schedule: { kind: "at", at_ms: Date.UTC(2026, 9, 15, 2) }, payload: { message: "Review the result" }, state: { next_run_at_ms: Date.UTC(2026, 9, 15, 2) } },
  { id: "gallery-weekly", name: "每周回顾", enabled: true, schedule: { kind: "every", every_ms: 604_800_000 }, payload: { message: "Review the week" }, state: {} },
];

function DeletePreview() {
  const { t } = useGalleryTranslation();
  const [scenario, setScenario] = useState<"single" | "multiple" | "automations">("single");
  const [open, setOpen] = useState(false);
  const [deleted, setDeleted] = useState(false);
  return <>
    <StatePicker label={t("previews.delete.scenario")} value={scenario} options={["single", "multiple", "automations"]}
      onChange={(next) => { setScenario(next); setDeleted(false); }} />
    <Button variant="outline" onClick={() => { setDeleted(false); setOpen(true); }}>{t("previews.delete.open")}</Button>
    <DeleteConfirm open={open} title="组件设计" count={scenario === "multiple" ? 3 : 1}
      automations={scenario === "automations" ? automations : []} onCancel={() => setOpen(false)}
      onConfirm={() => { setDeleted(true); setOpen(false); }} />
    <p role="status" className="mt-4 text-xs text-muted-foreground">{t(deleted ? "previews.delete.confirmed" : "previews.delete.hint")}</p>
  </>;
}

function InlineTokensPreview() {
  const { t } = useGalleryTranslation();
  const [command, setCommand] = useState("/status");
  const [handle, setHandle] = useState("gallery-session");
  return <div className="space-y-5">
    <Sample label={t("previews.inlineTokens.command")}><Input aria-label={t("previews.inlineTokens.command")} value={command} onChange={(event) => setCommand(event.target.value)} />
      <p className="text-sm"><Trans t={t} i18nKey="previews.inlineTokens.run" components={{ command: <SlashCommandText command={command} /> }} /></p></Sample>
    <Sample label={t("previews.inlineTokens.handle")}><Input aria-label={t("previews.inlineTokens.handle")} value={handle} onChange={(event) => setHandle(event.target.value)} />
      <p className="text-sm"><Trans t={t} i18nKey="previews.inlineTokens.continue" components={{ session: <SessionHandleLabel id={handle}>@design</SessionHandleLabel> }} /></p></Sample>
    <Sample label={t("previews.inlineTokens.highlight")}><p className="text-sm"><Trans t={t} i18nKey="previews.inlineTokens.review" components={{ skill: <InlineTokenHighlight color={INLINE_TOKEN_HIGHLIGHT_COLOR} title={t("previews.inlineTokens.skill", { name: "review" })}>review</InlineTokenHighlight> }} /></p></Sample>
  </div>;
}

function SessionLinksPreview({ children }: { children: ReactNode }) {
  const { t } = useGalleryTranslation();
  const [selected, setSelected] = useState(false);
  return <div className="space-y-4" onClick={(event) => {
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest<HTMLAnchorElement>('a[href^="#/chat/"]');
    if (!link) return;
    event.preventDefault();
    setSelected(true);
  }}>
    {children}
    <p role="status" className="text-xs text-muted-foreground">{selected ? t("previews.sessionLinks.selected", { name: sessionMention.title }) : t("previews.sessionLinks.hint")}</p>
  </div>;
}

function UserTextPreview() {
  const { t } = useGalleryTranslation();
  const [text, setText] = useState("用 $review 检查 @cirno 的修改，参考 @design 和 @files。");
  return <SessionLinksPreview>
    <label className="grid gap-2 text-xs text-muted-foreground">{t("previews.userText.message")}
      <Textarea value={text} onChange={(event) => setText(event.target.value)} />
    </label>
    <p className="whitespace-pre-wrap text-sm leading-7"><UserMessageText text={text} cliApps={[cliApp]}
      mcpPresets={[mcpPreset]} sessionMentions={[sessionMention]} /></p>
  </SessionLinksPreview>;
}

function CapabilityTokensPreview() {
  const { t } = useGalleryTranslation();
  const [variant, setVariant] = useState<"message" | "composer">("message");
  const segments: Array<Exclude<CapabilityMentionSegment, { kind: "text" }>> = [
    { kind: "cli", text: "@cirno", app: cliApp },
    { kind: "mcp", text: "@files", preset: mcpPreset },
    { kind: "session", text: "@design", mention: sessionMention },
  ];
  return <SessionLinksPreview>
    <StatePicker label={t("previews.capabilityTokens.position")} value={variant} options={["message", "composer"]} onChange={setVariant} />
    <div className="flex flex-wrap gap-6 text-sm leading-7">{segments.map((segment) =>
      <CapabilityMentionToken key={segment.kind} segment={segment} variant={variant} />)}</div>
  </SessionLinksPreview>;
}

function ProductIconsPreview() {
  const { t } = useGalleryTranslation();
  const [size, setSize] = useState<"16" | "20" | "24">("20");
  const [selected, setSelected] = useState("ConversationIcon");
  return <>
    <StatePicker label={t("previews.productIcons.size")} value={size} options={["16", "20", "24"]} onChange={setSize} />
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">{Object.entries(ProductIcons).map(([name, Icon]) =>
      <button key={name} type="button" aria-pressed={selected === name} onClick={() => setSelected(name)}
        className={cn("flex min-w-0 flex-col items-center gap-2 rounded-control p-3 text-muted-foreground hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", selected === name && "bg-surface-secondary text-foreground")}>
        <Icon size={Number(size)} /><span className="max-w-full break-all text-center text-[10px] leading-4">{name.replace(/Icon$/, "")}</span>
      </button>)}</div>
    <p role="status" className="mt-4 text-xs text-muted-foreground">{t("previews.productIcons.selected", { name: selected })}</p>
  </>;
}

function StartupPreview() {
  return <div className="gallery-startup-preview h-80 overflow-hidden rounded-panel border"><StartupShell embedded /></div>;
}

function FileActionsPreview() {
  const { t } = useGalleryTranslation();
  const [scope, setScope] = useState<"workspace" | "outside" | "unresolved">("workspace");
  const path = "src/app.tsx";
  return <>
    <StatePicker label={t("previews.fileActions.scope")} value={scope} options={["workspace", "outside", "unresolved"]} onChange={setScope} />
    <FileActions path={path} metadata={scope === "unresolved" ? undefined : {
      path: scope === "workspace" ? "D:/workspace/cirno/src/app.tsx" : "D:/documents/report.tsx",
      relative_path: scope === "workspace" ? path : null,
    }}><Button variant="outline">{path}</Button></FileActions>
    <p className="mt-4 text-xs text-muted-foreground">{t("previews.fileActions.hint")}</p>
  </>;
}

const components = "sources/cirno-web/src/components/";
export const shellExamples: ComponentExample[] = [
  { title: "previews.delete.title", files: ["DeleteConfirm"], Preview: DeletePreview,
    description: "previews.delete.description", options: "previews.delete.options",
    code: '<DeleteConfirm open={open} title="组件设计" count={1} automations={jobs} onCancel={close} onConfirm={remove} />' },
  { title: "previews.inlineTokens.title", files: ["SlashCommandText", "InlineTokenHighlight", "SessionHandleLabel"], Preview: InlineTokensPreview,
    description: "previews.inlineTokens.description", options: "previews.inlineTokens.options",
    code: '<SlashCommandText command="/status" />\n<SessionHandleLabel id={session.id}>@design</SessionHandleLabel>\n<InlineTokenHighlight color="var(--inline-token-highlight)">review</InlineTokenHighlight>' },
  { title: "previews.userText.title", files: ["UserMessageText"], Preview: UserTextPreview,
    description: "previews.userText.description", options: "previews.userText.options",
    code: '<UserMessageText text={text} cliApps={apps} mcpPresets={presets} sessionMentions={sessions} />' },
  { title: "previews.capabilityTokens.title", files: ["CliAppMentionText"], Preview: CapabilityTokensPreview,
    description: "previews.capabilityTokens.description", options: "previews.capabilityTokens.options",
    code: '<CapabilityMentionToken segment={{ kind: "cli", text: "@cirno", app }} variant="message" />' },
  { title: "previews.productIcons.title", files: ["icons/product-icons"], Preview: ProductIconsPreview,
    description: "previews.productIcons.description", options: "previews.productIcons.options",
    code: '<ConversationIcon size={20} />\n<SettingsIcon className="text-muted-foreground" />' },
  { title: "previews.startup.title", files: ["StartupShell"], Preview: StartupPreview,
    description: "previews.startup.description", options: "previews.startup.options",
    code: '<StartupShell embedded />' },
  { title: "previews.fileActions.title", files: ["FileActions"], Preview: FileActionsPreview,
    description: "previews.fileActions.description", options: "previews.fileActions.options",
    code: '<FileActions path="src/app.tsx" metadata={{ path: "D:/workspace/src/app.tsx", relative_path: "src/app.tsx" }}><Button>app.tsx</Button></FileActions>' },

].map((example) => ({ ...example, files: example.files.map((file) => `${components}${file}.tsx`) }));
