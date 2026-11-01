import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { BookOpen, History, RefreshCw, Search, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsSectionTitle } from "./shared/SettingsControls";
import type { CirnoClient } from "@/lib/cirno-client";

type MemoryRecord = { id: string; title: string; source: string; owner_title?: string; project_id?: string; session_key?: string; scope: string; layer: string; kind: string;
  revision: number; observed_at?: string | null; created_at?: string; status: string; tags: string[]; snippet?: string; content?: string; updated_at: string;
  links?: { source: string; target: string; relation: string; evidence: string }[] };
type MemoryStatus = { counts: Record<string, number>; pending: number; failed: number; index_bytes: number;
  databases?: Record<string, number>; receipts?: { memory_id: string; outcome: string; reason: string; input_revision: number }[];
  last_dream: { at: string; error?: string; created?: number; merged?: number; skipped?: number; retained?: number } | null; failures?: { memory_id: string; revision: number; attempts: number; error: string | null }[] };
type SearchResult = { memories: MemoryRecord[]; has_more: boolean; next_offset: number; time_zone?: string; engine?: string; warning_code?: string; warning?: string; embedding_index_pending?: boolean };
type SourcePage = { memory_id?: string; source: string; note?: string; content?: string; source_refs?: { memory_id?: string; source?: string; start_line?: number; revision?: number }[];
  lines?: { line: number; text: string; next_char_offset?: number | null }[]; next_line?: number | null };

function MemoryEntry({ client, memory }: { client: CirnoClient; memory: MemoryRecord }) {
  const { t } = useTranslation();
  const tr = (key: string) => t(`memoryLibrary.${key}`);
  const [record, setRecord] = useState<MemoryRecord | null>(null);
  const [versions, setVersions] = useState<MemoryRecord[]>([]);
  const [source, setSource] = useState<SourcePage | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const request = async (action: string, values: Record<string, unknown> = {}) => {
    setBusy(true); setError("");
    try {
      if (action === "memory.read") setRecord(await client.requestMutation<MemoryRecord>("instance.action", { action, values: { id: memory.id, ...values } }));
      if (action === "memory.history") setVersions((await client.requestMutation<{ revisions: MemoryRecord[] }>("instance.action", { action, values: { id: memory.id } })).revisions);
      if (action === "memory.source") setSource(await client.requestMutation<SourcePage>("instance.action", { action, values: { id: memory.id, ...values } }));
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  };
  return <details className="rounded-control bg-settings-surface px-4 py-3">
    <summary className="cursor-pointer text-sm marker:text-muted-foreground" onClick={() => { if (!record && !busy) void request("memory.read"); }}>
      <span className="ml-1 break-words font-medium">{memory.layer === "source" ? `${tr("archivedEvidenceTitle")} · ${new Date(memory.updated_at).toLocaleString()} · ${memory.id.slice(-6)}` : memory.title === "Task checkpoint" ? tr("taskCheckpoint") : memory.title}</span>
      <span className="mt-1 block break-words text-xs text-muted-foreground">{tr(memory.layer)} · {tr(memory.scope)} · {tr(memory.status)} · {t("memoryLibrary.revision", { revision: memory.revision })}</span>
    </summary>
    <div className="mt-3 min-w-0 space-y-3">
      {error && <p role="alert" className="break-words text-sm text-destructive">{error}</p>}
      {memory.scope !== "user" && <p className="break-words text-xs text-muted-foreground">{memory.owner_title ?? memory.project_id ?? memory.session_key}</p>}
      {record?.observed_at && <p className="text-xs text-muted-foreground">{tr("observedAt")}: {record.observed_at}</p>}
      <p className="break-all text-xs text-muted-foreground">{memory.id} · {new Date(memory.updated_at).toLocaleString()}<br />{record?.source ?? memory.source}</p>
      {memory.tags.length > 0 && <p className="break-words text-xs text-muted-foreground">{memory.tags.join(" · ")}</p>}
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-sm">{record?.content ?? memory.snippet}</pre>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="ghost" className="gap-2" disabled={busy} onClick={() => void request("memory.history")}><History className="size-4" />{tr("history")}</Button>
        <Button size="sm" variant="ghost" className="gap-2" disabled={busy} onClick={() => void request("memory.source", { revision: record?.revision ?? memory.revision })}><ExternalLink className="size-4" />{tr("evidence")}</Button>
      </div>
      {versions.length > 0 && <div className="flex flex-wrap gap-2">{versions.map((version) => <Button key={version.revision} size="sm" variant={record?.revision === version.revision ? "secondary" : "ghost"} disabled={busy} onClick={() => void request("memory.read", { revision: version.revision })}>{t("memoryLibrary.revision", { revision: version.revision })}</Button>)}</div>}
      {!!record?.links?.length && <div className="text-xs"><p className="mb-1 font-medium">{tr("links")}</p>{record.links.map((link) => <p className="break-all" key={`${link.source}-${link.target}-${link.relation}`}>{link.relation}: {link.source} → {link.target}<br />{link.evidence}</p>)}</div>}
      {source && <div className="rounded-control border border-border p-3 text-xs">
        <p className="mb-2 break-all font-medium">{source.source}</p>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words">{source.content ?? source.lines?.map((line) => `${line.line}: ${line.text}`).join("\n") ?? source.note}</pre>
        {source.source_refs?.filter((ref) => ref.memory_id).map((ref) => <Button key={ref.memory_id} size="sm" variant="ghost" disabled={busy} className="max-w-full gap-2 text-xs" onClick={() => void request("memory.source", { id: ref.memory_id, revision: ref.revision, start_line: ref.start_line ?? 1 })}><BookOpen className="size-3.5 shrink-0" /><span className="truncate">{tr("archivedEvidenceTitle")} · {ref.memory_id?.slice(-6)}</span></Button>)}
        {!!source.lines?.length && (source.next_line != null || source.lines[source.lines.length - 1].next_char_offset != null) && <Button size="sm" variant="ghost" disabled={busy} onClick={() => {
          const last = source.lines![source.lines!.length - 1];
          void request("memory.source", { id: source.memory_id ?? memory.id, start_line: last.next_char_offset != null ? last.line : source.next_line, char_offset: last.next_char_offset ?? 0 });
        }}>{tr("sourceMore")}</Button>}
      </div>}
    </div>
  </details>;
}

export function MemorySourcesSettings({ client }: { client: CirnoClient }) {
  const { t } = useTranslation();
  const tr = (key: string) => t(`memoryLibrary.${key}`);
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [status, setStatus] = useState<MemoryStatus | null>(null);
  const [query, setQuery] = useState("");
  const [tags, setTags] = useState("");
  const [mode, setMode] = useState("bm25");
  const [retrieval, setRetrieval] = useState<SearchResult | null>(null);
  const [tagOptions, setTagOptions] = useState<{ name: string; count: number }[]>([]);
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [timeField, setTimeField] = useState("observed_at");
  const [dateTimezone, setDateTimezone] = useState("UTC");
  const [layer, setLayer] = useState("all");
  const [scope, setScope] = useState("all");
  const [includeHistory, setIncludeHistory] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [rebuildMore, setRebuildMore] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const cancelRebuild = useRef(false);
  const requestSequence = useRef(0);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = useCallback(async (offset = 0, selectedTags = tags) => {
    const sequence = ++requestSequence.current;
    setBusy(true);
    try {
      const [result, stats] = await Promise.all([
        client.requestMutation<SearchResult>("instance.action", {
          action: "memory.list", values: { query, mode, layer, scope, since: since || undefined, until: until || undefined, time_field: timeField, tags: selectedTags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean), include_history: includeHistory, limit: 10, offset },
        }),
        client.requestMutation<MemoryStatus>("instance.action", { action: "memory.status" }),
      ]);
      if (sequence !== requestSequence.current) return;
      if (!Array.isArray(result.memories) || !stats.counts) throw new Error("Invalid memory response; refresh the gateway connection.");
      setMemories((old) => offset ? [...old, ...result.memories] : result.memories);
      setDateTimezone(result.time_zone ?? "UTC");
      setRetrieval(query.trim() ? result : null);
      setNextOffset(result.has_more ? result.next_offset : null); setStatus(stats); setError("");
    } catch (reason) { if (sequence === requestSequence.current) { setError((reason as Error).message); setRetrieval(null); } }
    finally { if (sequence === requestSequence.current) setBusy(false); }
  }, [client, query, mode, layer, scope, tags, includeHistory, since, until, timeField]);
  // Search is explicit; editing a query does not send a request on every keystroke.
  useEffect(() => { void reload(); }, [client, mode, layer, scope, includeHistory]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { cancelRebuild.current = true; requestSequence.current += 1; }, [client]);
  const discoverTags = async () => {
    try {
      const result = await client.requestMutation<{ tags: { name: string; count: number }[] }>("instance.action", { action: "memory.tags", values: { limit: 30 } });
      setTagOptions(result.tags); setError("");
    } catch (reason) { setError((reason as Error).message); }
  };
  const maintain = async (action: string) => {
    setBusy(true); setError("");
    try {
      if (action === "memory.reindex") {
        cancelRebuild.current = false; setRebuilding(true);
        let more = true; let scanned = 0;
        while (more && !cancelRebuild.current) {
          const result = await client.requestMutation<{ has_more: boolean; scanned: number }>("instance.action", { action });
          more = result.has_more; scanned += result.scanned ?? 0;
          setNotice(t("memoryLibrary.rebuildProgress", { count: scanned }));
        }
        setRebuildMore(more); setNotice(more ? tr("rebuildMore") : tr("rebuildDone"));
      } else await client.requestMutation("instance.action", { action });
      await reload();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); setRebuilding(false); }
  };
  return <section className="min-w-0 space-y-3">
    <div className="settings-section-heading">
      <SettingsSectionTitle>{t("features.memorySources")}</SettingsSectionTitle>
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => void reload()} aria-label={t("features.refresh")}><RefreshCw className={`size-4 ${busy ? "animate-spin" : ""}`} /></Button>
    </div>
    {status && <div className="rounded-control bg-settings-surface p-4 text-xs text-muted-foreground">
      <div className="flex flex-wrap gap-x-4 gap-y-2"><span>{t("memoryLibrary.indexed", { count: Object.values(status.counts).reduce((a, b) => a + b, 0) })}</span><span>{t("memoryLibrary.pending", { count: status.pending })}</span><span>{t("memoryLibrary.failed", { count: status.failed })}</span><span>{t("memoryLibrary.indexSize", { size: (status.index_bytes / 1048576).toFixed(1) })}</span></div>
      <p className="mt-2 break-words">{tr("lastDream")}: {status.last_dream ? new Date(status.last_dream.at).toLocaleString() : tr("noDream")}{status.last_dream?.error && ` · ${status.last_dream.error}`}</p>
      {!!status.receipts?.length && <details className="mt-2"><summary className="cursor-pointer">{tr("dreamOutcomes")}</summary><div className="mt-2 space-y-2">{status.receipts.map((receipt, index) => <p className="break-words" key={`${receipt.memory_id}-${index}`}>{tr(`${receipt.outcome}Outcome`)} · {receipt.memory_id.slice(-6)} · {t("memoryLibrary.revision", { revision: receipt.input_revision })}<br />{receipt.reason}</p>)}</div></details>}
      {status.databases && <details className="mt-2"><summary className="cursor-pointer">{tr("databases")}</summary>{Object.entries(status.databases).map(([name, bytes]) => <p className="mt-1" key={name}>{name} · {(bytes / 1048576).toFixed(2)} MB</p>)}</details>}
      {!!status.failures?.length && <details className="mt-2"><summary className="cursor-pointer">{t("memoryLibrary.failed", { count: status.failed })}</summary><div className="mt-2 space-y-2">{status.failures.map((failure) => <p className="break-all" key={failure.memory_id}>{failure.memory_id} · {t("memoryLibrary.revision", { revision: failure.revision })}<br />{failure.error ?? tr("interrupted")}</p>)}</div></details>}
      <div className="mt-2 flex flex-wrap gap-2"><Button size="sm" variant="ghost" className="gap-2" disabled={busy} onClick={() => void maintain("memory.reindex")}><RefreshCw className="size-3.5" />{tr(rebuildMore ? "rebuildMore" : "reindex")}</Button>{rebuilding && <Button size="sm" variant="ghost" onClick={() => { cancelRebuild.current = true; }}>{t("features.stop")}</Button>}{status.failed > 0 && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void maintain("memory.retry")}>{tr("retry")}</Button>}</div>
    </div>}
    <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void reload(); }}>
      <div className="flex min-w-0 gap-2"><Input aria-label={tr("search")} placeholder={tr("search")} value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1" /><Button type="submit" size="icon" variant="ghost" disabled={busy} aria-label={tr("search")}><Search className="size-4" /></Button></div>
      <Select value={mode} onValueChange={setMode} disabled={busy}><SelectTrigger aria-label={tr("searchMode")} className="w-full min-w-0"><SelectValue /></SelectTrigger><SelectContent>{["bm25", "semantic", "hybrid"].map((option) => <SelectItem key={option} value={option}>{tr(`${option}Mode`)}</SelectItem>)}</SelectContent></Select>
      <div className="grid grid-cols-2 gap-2">
        {([[layer, setLayer, "layer", ["all", "event", "knowledge", "task", "source", "profile"]], [scope, setScope, "scope", ["all", "user", "project", "session"]]] as const).map(([value, setter, label, options]) => <Select key={label} value={value} onValueChange={setter} disabled={busy}><SelectTrigger aria-label={tr(label)} className="w-full min-w-0"><SelectValue /></SelectTrigger><SelectContent>{options.map((option) => <SelectItem key={option} value={option}>{tr(option)}</SelectItem>)}</SelectContent></Select>)}
      </div>
      <div className="flex min-w-0 gap-2"><Input aria-label={tr("tags")} placeholder={tr("tags")} value={tags} onChange={(event) => setTags(event.target.value)} className="min-w-0 flex-1" /><Button type="button" size="sm" variant="ghost" onClick={() => void discoverTags()}>{tr("discoverTags")}</Button></div>
      {!!tagOptions.length && <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto rounded-control border border-border p-2">{tagOptions.map((tag) => <Button type="button" key={tag.name} size="sm" variant="ghost" className="max-w-full" onClick={() => { setTags(tag.name); setTagOptions([]); void reload(0, tag.name); }}><span className="truncate">{tag.name} · {tag.count}</span></Button>)}</div>}
      <details className="px-2 text-xs text-muted-foreground"><summary className="cursor-pointer py-1">{tr("timeField")}</summary><div className="mt-2 space-y-2">
        <Select value={timeField} onValueChange={setTimeField}><SelectTrigger aria-label={tr("timeField")}><SelectValue /></SelectTrigger><SelectContent>{(["observed_at", "created_at", "updated_at"] as const).map((field) => <SelectItem key={field} value={field}>{tr(({ observed_at: "observedAt", created_at: "createdAt", updated_at: "updatedAt" })[field])}</SelectItem>)}</SelectContent></Select>
        <p>{dateTimezone}</p><div className="grid grid-cols-2 gap-2"><label className="min-w-0">{tr("since")}<Input type="date" aria-label={tr("since")} value={since} onInput={(event) => setSince(event.currentTarget.value)} onChange={(event) => setSince(event.target.value)} className="min-w-0 w-full" /></label><label className="min-w-0">{tr("until")}<Input type="date" aria-label={tr("until")} value={until} onInput={(event) => setUntil(event.currentTarget.value)} onChange={(event) => setUntil(event.target.value)} className="min-w-0 w-full" /></label></div>
        <Button type="submit" size="sm" variant="ghost">{tr("filterAction")}</Button>
      </div></details>
      <Button type="button" size="sm" className="gap-2" variant={includeHistory ? "secondary" : "ghost"} aria-pressed={includeHistory} onClick={() => setIncludeHistory(!includeHistory)}><History className="size-3.5" />{tr("includeHistory")}</Button>
    </form>
    {retrieval && <div role="status" className="space-y-1 break-words px-2 text-xs text-muted-foreground">
      {retrieval.engine && <p>{t("memoryLibrary.searchEngine", { mode: tr(`${retrieval.engine}Mode`) })}</p>}
      {retrieval.warning_code && <p>{tr(`fallback_${retrieval.warning_code}`)}</p>}
      {retrieval.warning && (!retrieval.warning_code || retrieval.warning_code === "unavailable") && <details><summary className="cursor-pointer">{tr("searchDetails")}</summary><p className="mt-1 break-all">{retrieval.warning}</p></details>}
      {retrieval.embedding_index_pending && <p>{tr("indexPending")}</p>}
    </div>}
    {error && <p role="alert" className="break-words text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="text-xs text-muted-foreground">{notice}</p>}
    {memories.length === 0 && <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><BookOpen className="size-4 shrink-0" />{t("features.noMemorySources")}</div>}
    {memories.map((memory) => <MemoryEntry key={`${memory.id}-${memory.revision}`} memory={memory} client={client} />)}
    {nextOffset !== null && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void reload(nextOffset)}>{tr("more")}</Button>}
  </section>;
}
