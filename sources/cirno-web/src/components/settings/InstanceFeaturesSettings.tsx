import { useTranslation } from "react-i18next";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Plus, Terminal, Play, Pencil, Trash2 } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { SettingsSectionTitle } from "@/components/settings/shared/SettingsControls";
import type { CirnoClient } from "@/lib/cirno-client";

type NodeRecord = {
  id?: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: "key" | "password";
  password?: string;
  has_password?: boolean;
  identity_file: string;
  working_directory: string;
  host_key: string;
};
type JobRecord = {
  id: string;
  node_id: string;
  state: string;
  command: string;
  output?: string;
  error?: string;
};
const EMPTY_NODE: NodeRecord = {
  name: "",
  host: "",
  port: 22,
  username: "",
  auth_method: "key",
  password: "",
  identity_file: "",
  working_directory: ".",
  host_key: "",
};

export function NodesSettings({ client }: { client: CirnoClient }) {
  const { t } = useTranslation();
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [draft, setDraft] = useState<NodeRecord | null>(null);
  const [executionNode, setExecutionNode] = useState<NodeRecord | null>(null);
  const [command, setCommand] = useState("");
  const [commandOutput, setCommandOutput] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const action = useCallback(
    <T,>(name: string, values: object = {}) =>
      client.requestMutation<T>("instance.action", { action: name, values }, name === "nodes.execute" ? 130_000 : 30_000),
    [client],
  );
  const reload = useCallback(async () => {
    const result = await action<{ nodes: NodeRecord[]; jobs: JobRecord[] }>(
      "nodes.list",
    );
    setNodes(result.nodes);
    setJobs(result.jobs);
  }, [action]);
  useEffect(() => {
    void reload().catch((reason) => setError((reason as Error).message));
  }, [reload]);
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="settings-stack">
      <div className="settings-section-heading">
        <SettingsSectionTitle>Nodes</SettingsSectionTitle>
        <Button size="sm" onClick={() => setDraft({ ...EMPTY_NODE })}>
          <Plus className="mr-1.5 h-4 w-4" aria-hidden />{t("features.addNode")}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        {t("features.nodesDescription")}
      </p>
      {error && (
        <p role="alert" className="break-words text-sm text-destructive">
          {error}
        </p>
      )}
      {notice && (
        <pre role="status" className="whitespace-pre-wrap break-all text-xs">
          {notice}
        </pre>
      )}
      <div className="divide-y divide-border rounded-panel bg-settings-surface px-4">
        {nodes.length === 0 && (
          <p className="py-6 text-sm text-muted-foreground">
            {t("features.noNodes")}
          </p>
        )}
        {nodes.map((node) => (
          <div key={node.id} className="flex flex-wrap items-center gap-2 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{node.name}</p>
              <p className="truncate text-xs text-muted-foreground">
                {node.username}@{node.host}:{node.port}
              </p>
            </div>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const result = await action<{ output: string }>(
                    "nodes.test",
                    { id: node.id },
                  );
                  setNotice(result.output);
                })
              }
            >
              {t("features.test")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setExecutionNode(node); setCommandOutput(""); }}>
              <Terminal className="mr-1.5 h-4 w-4" aria-hidden />{t("features.executeCommand")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDraft({ ...node, password: "" })}
            >
              <Pencil className="mr-1.5 h-4 w-4" aria-hidden />{t("features.edit")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await action("nodes.delete", { id: node.id });
                  await reload();
                })
              }
            >
              <Trash2 className="mr-1.5 h-4 w-4" aria-hidden />{t("features.delete")}
            </Button>
          </div>
        ))}
      </div>
      {executionNode && (
        <form className="space-y-4 rounded-panel bg-settings-surface p-4" onSubmit={(event) => {
          event.preventDefault();
          void run(async () => {
            const result = await action<{ output: string }>("nodes.execute", { id: executionNode.id, command });
            setCommandOutput(result.output || t("features.commandCompleted"));
          });
        }}>
          <p className="text-sm font-medium">{executionNode.name}</p>
          <label className="block space-y-2 text-sm">{t("features.command")}
            <Textarea required value={command} onChange={event => setCommand(event.target.value)} className="font-mono" />
          </label>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !command.trim()}><Play className="mr-1.5 h-4 w-4" aria-hidden />{t("features.runCommand")}</Button>
            <Button type="button" variant="ghost" disabled={busy} onClick={() => setExecutionNode(null)}>{t("features.close")}</Button>
          </div>
          {commandOutput && <pre role="status" className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-control bg-background p-3 font-mono text-xs">{commandOutput}</pre>}
        </form>
      )}
      {draft && (
        <form
          className="space-y-4 rounded-panel bg-settings-surface p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void run(async () => {
              await action("nodes.save", draft);
              setDraft(null);
              await reload();
            });
          }}
        >
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr))]">
            {(
              [
                ["name", t("features.name")],
                ["host", t("features.host")],
                ["username", t("features.sshUser")],
                ["working_directory", t("features.remoteDirectory")],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="space-y-1 text-sm">
                {label}
                <Input
                  required
                  value={draft[key]}
                  onChange={(event) =>
                    setDraft({ ...draft, [key]: event.target.value })
                  }
                />
              </label>
            ))}
            <label className="space-y-1 text-sm">
              {t("features.sshPort")}
              <Input
                type="number"
                min={1}
                max={65535}
                required
                value={draft.port}
                onChange={(event) =>
                  setDraft({ ...draft, port: Number(event.target.value) })
                }
              />
            </label>
          </div>
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr))]">
            <label className="block space-y-2 text-sm">{t("features.authentication")}
              <Select value={draft.auth_method} onValueChange={(value: "key" | "password") => setDraft({ ...draft, auth_method: value })}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="key">{t("features.keyAuthentication")}</SelectItem><SelectItem value="password">{t("features.passwordAuthentication")}</SelectItem></SelectContent>
              </Select>
            </label>
            {draft.auth_method === "password" ? <label className="block space-y-2 text-sm">{t("features.password")}
              <Input type="password" autoComplete="new-password" required={!draft.has_password} placeholder={draft.has_password ? t("features.keepPassword") : undefined} value={draft.password || ""} onChange={event => setDraft({ ...draft, password: event.target.value })} />
            </label> : <label className="block space-y-2 text-sm">{t("features.identityFile")}
              <Input value={draft.identity_file} onChange={event => setDraft({ ...draft, identity_file: event.target.value })} />
            </label>}
          </div>
          <label className="block space-y-1 text-sm">
            {t("features.hostKey")}
            <Textarea
              value={draft.host_key}
              onChange={(event) =>
                setDraft({ ...draft, host_key: event.target.value })
              }
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy || !draft.host}
              onClick={() =>
                void run(async () => {
                  const result = await action<{
                    host_key: string;
                    fingerprints: string;
                  }>("nodes.scan", { host: draft.host, port: draft.port });
                  setDraft({ ...draft, host_key: result.host_key });
                  setNotice(
                    t("features.fingerprintNotice") +
                      "\n" +
                      result.fingerprints,
                  );
                })
              }
            >
              {t("features.scanKey")}
            </Button>
            <Button type="submit" disabled={busy}>
              {t("features.save")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDraft(null)}
            >
              {t("features.cancel")}
            </Button>
          </div>
        </form>
      )}
      <div className="settings-section-heading">
        <SettingsSectionTitle>{t("features.jobs")}</SettingsSectionTitle>
        <Button variant="ghost" size="sm" onClick={() => void run(reload)}>
          {t("features.refreshList")}
        </Button>
      </div>
      {jobs.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("features.noJobs")}</p>
      )}
      {jobs.map((job) => (
        <div
          key={job.id}
          className="space-y-2 rounded-panel bg-settings-surface p-4"
        >
          <p className="break-all text-sm">{job.command}</p>
          <p className="text-xs text-muted-foreground">
            {job.state} · {job.id}
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await action("nodes.job", { id: job.id });
                  await reload();
                })
              }
            >
              {t("features.readStatus")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await action("nodes.stop", { id: job.id });
                  await reload();
                })
              }
            >
              {t("features.stop")}
            </Button>
          </div>
          {(job.output || job.error) && (
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all text-xs">
              {job.error || job.output}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

export { MemorySourcesSettings } from "./MemorySourcesSettings";

export function SkillHistorySettings({ client }: { client: CirnoClient }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [result, setResult] = useState<{
    validation: { valid: boolean; errors: string[] };
    versions: {
      revision: string;
      path: string;
      validation: { valid: boolean; errors: string[] };
    }[];
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <section className="space-y-3">
      <SettingsSectionTitle>{t("features.skillHistory")}</SettingsSectionTitle>
      <form
        className="flex gap-2"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            setResult(
              await client.requestMutation("instance.action", {
                action: "skills.validate",
                values: { name },
              }),
            );
          } catch (reason) {
            setError((reason as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Input
          aria-label={t("features.skillName")}
          placeholder={t("features.skillName")}
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Button disabled={busy} type="submit">
          {t("features.validate")}
        </Button>
      </form>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {result && (
        <>
          <p className="text-sm">
            {result.validation.valid
              ? t("features.validationPassed")
              : result.validation.errors.join("\n")}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("features.validationDescription")}
          </p>
          {result.versions.map((version) => (
            <details
              key={version.revision}
              className="rounded-control bg-settings-surface p-3"
            >
              <summary className="cursor-pointer truncate text-xs">
                {version.revision}
              </summary>
              <p className="mt-2 break-all text-xs">{version.path}</p>
              <p className="text-xs">
                {version.validation.valid
                  ? t("features.valid")
                  : version.validation.errors.join("\n")}
              </p>
            </details>
          ))}
        </>
      )}
    </section>
  );
}
