import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { MemoryLibrary } from "@/features/memory/MemoryLibrary";
import { ProfileFiles } from "@/features/profile/ProfileFiles";
import type { WebUIMutationTransport } from "@/lib/api";
import { useTheme } from "@/hooks/useTheme";

const memory = {
  id: "calibration",
  title: "Detector calibration",
  source: "memory/knowledge/calibration.md",
  scope: "project",
  owner_title: "Long duration research",
  layer: "knowledge",
  kind: "fact",
  revision: 2,
  status: "active",
  tags: ["calibration", "detector"],
  updated_at: "2026-11-07T00:00:00Z",
  observed_at: "2026-10-31T08:00:00Z",
  snippet:
    "Exact measured temperature: 25.125 °C. Research findings remain linked to their original evidence.",
};
export function MemoryFixture() {
  useTheme();
  const { t } = useTranslation();
  const [calls, setCalls] = useState<{ action: string; values?: Record<string, unknown> }[]>([]);
  const profileOnly = new URLSearchParams(location.search).has("profile");
  const client = useMemo(() => {
    let sourceAttempts = 0,
      saves = 0,
      revision = 1;
    const requestMutation = async (
      method: string,
      params: { action?: string; name?: string; content?: string; values?: Record<string, unknown> },
    ) => {
      const { action = method, values = {} } = params;
      setCalls((previous) => [...previous, { action, values }]);
      if (method === "settings.profile.read")
        return {
          name: params.name,
          file: `${params.name?.toUpperCase()}.md`,
          content: "Maintain exact measurements.\nKeep the original evidence.\n".repeat(12),
          revision: `r${revision}`,
        };
      if (method === "settings.profile.update") {
        if (++saves === 1) throw new Error("File changed; reload before saving");
        return {
          name: params.name,
          file: `${params.name?.toUpperCase()}.md`,
          content: params.content,
          revision: `r${++revision}`,
        };
      }
      if (action === "memory.status")
        return {
          counts: { knowledge: 12, source: 28, task: 3 },
          pending: 2,
          failed: 1,
          index_bytes: 1572864,
          last_dream: { at: "2026-11-07T08:00:00Z", error: "Embedding endpoint timed out" },
          databases: { "catalog.sqlite3": 1024000, "search.sqlite3": 2048000 },
        };
      if (action === "memory.list")
        return {
          memories: [
            { ...memory, ...(values.offset ? { id: "second", title: "Follow-up measurement" } : {}) },
          ],
          has_more: !values.offset,
          next_offset: 10,
          time_zone: "Asia/Shanghai",
          engine: "bm25",
          ...(values.mode === "semantic" ? { warning_code: "disabled" } : {}),
        };
      if (action === "memory.read")
        return {
          ...memory,
          revision: values.revision,
          content:
            values.revision === 1
              ? "Original temperature: 30.25 °C"
              : "Exact temperature: 25.125 °C\n".repeat(20),
          links: [],
        };
      if (action === "memory.history") return { revisions: [{ ...memory, revision: 1 }] };
      if (action === "memory.source") {
        if (values.char_offset && ++sourceAttempts === 1)
          throw new Error("Evidence page temporarily unavailable");
        return {
          memory_id: "captured-source",
          revision: 7,
          source: "memory/sources/captured-source.jsonl",
          lines: [
            {
              line: 4,
              text: values.char_offset
                ? "Continuation: exact original measurement"
                : "temperature=25.125 °C; ".repeat(900).slice(0, 16000),
              next_char_offset: values.char_offset ? null : 16000,
            },
          ],
          next_line: null,
        };
      }
      if (action === "memory.tags")
        return {
          tags: [
            { name: "calibration", count: 12 },
            { name: "detector", count: 6 },
          ],
        };
      if (action === "memory.reindex") return { scanned: 100, has_more: false };
      if (action === "memory.retry") return { retried: 1 };
      throw new Error(`Unhandled fixture action: ${action}`);
    };
    return { requestMutation } as WebUIMutationTransport;
  }, []);
  return (
    <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-xl font-semibold">
          {t(profileOnly ? "settings.nav.personality" : "settings.nav.memory")}
        </h1>
        <ProfileFiles client={client} section={profileOnly ? "personality" : "memory"} />
        {!profileOnly && <MemoryLibrary client={client} />}
        <output hidden data-testid="memory-calls">
          {JSON.stringify(calls)}
        </output>
      </div>
    </main>
  );
}
