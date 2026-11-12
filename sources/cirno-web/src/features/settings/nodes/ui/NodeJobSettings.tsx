import { Alert, Description, Input, Label, TextField } from "@heroui/react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { CirnoClient } from "@/lib/cirno-client";
import { useLifetime } from "@/ui/resources/useLifetime";
import type { NodeJobSettings as Policy } from "../model/contracts";
import type { NodesController } from "../model/useNodes";

const fields = ["poll_interval_seconds", "retention_days"] as const;

export function NodeJobSettings({ nodes, client }: { nodes: NodesController; client: CirnoClient }) {
  const { t } = useTranslation();
  const current = useLifetime(client);
  const [draft, setDraft] = useState<Partial<Record<keyof Policy, string>>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const pending = useRef(false);
  const commit = async (field: keyof Policy) => {
    const submitted = draft[field];
    if (submitted === undefined || pending.current) return;
    const value = Number(submitted);
    if (!/^\d+$/.test(submitted.trim()) || !Number.isSafeInteger(value) || value < 0) {
      setError(t("features.nodeJobInteger")); return;
    }
    pending.current = true; setSaving(true); setError("");
    try {
      await nodes.saveJobSettings({ [field]: value });
      if (current()) setDraft(previous => previous[field] === submitted ? { ...previous, [field]: undefined } : previous);
    } catch (reason) {
      if (current()) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      pending.current = false;
      if (current()) setSaving(false);
    }
  };
  return <section className="node-job-policy" aria-label={t("features.nodeJobPolicy")} aria-busy={saving}>
    <h2>{t("features.nodeJobPolicy")}</h2>
    <p className="node-help">{t("features.nodeJobPolicyHelp")}</p>
    {fields.map(field => <TextField key={field} className="node-job-policy-field" isDisabled={saving}
      value={draft[field] ?? String(nodes.jobSettings[field])} onBlur={() => { void commit(field); }}
      onChange={value => { setDraft(previous => ({ ...previous, [field]: value })); setError(""); }}>
      <div className="node-job-policy-copy"><Label>{t(`features.nodeJobPolicyFields.${field}`)}</Label><Description>{t(`features.nodeJobPolicyHelpFields.${field}`)}</Description></div>
      <Input type="number" min={0} max={Number.MAX_SAFE_INTEGER} step={1}
        onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); void commit(field); } }} />
    </TextField>)}
    {error && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
  </section>;
}
