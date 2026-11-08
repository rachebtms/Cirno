import { useEffect, useRef, useState } from "react";
import { emptyCustomProviderDraft, CUSTOM_PROVIDER_CREATION_KEY } from "../providerForm";
import type { ProviderSettingsProps } from "./contracts";
export type ProviderSetupStep = { kind: "list" | "picker" | "custom" } | { kind: "provider"; id: string; adding: boolean };

export function useProviderSetup(props: ProviderSettingsProps) {
  const [step, setStep] = useState<ProviderSetupStep>(() => props.entry.kind === "edit"
    ? { kind: "provider", id: props.entry.provider, adding: false }
    : { kind: props.entry.kind === "manage" ? "list" : "picker" });
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState(emptyCustomProviderDraft);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const lastProvider = useRef<string | null>(null);
  const provider = step.kind === "provider" ? props.settings.providers.find(row => row.id === step.id) : undefined;
  const busy = Boolean(props.providerSaving) || submitting;
  const reset = () => { if (step.kind === "provider") props.onResetProviderDraft(step.id); };
  const close = () => { reset(); props.onClose(); };
  const back = () => {
    if (props.entry.origin === "providers" && (step.kind === "picker" || step.kind === "provider" && !step.adding)) { close(); return; }
    reset(); setError("");
    setStep({ kind: step.kind === "custom" || step.kind === "provider" && step.adding ? "picker" : "list" });
  };
  const returnToOrigin = () => { if (props.entry.kind === "manage") setStep({ kind: "list" }); else close(); };
  const edit = (id: string, adding: boolean) => { props.onResetProviderDraft(id); lastProvider.current = id; setError(""); setStep({ kind: "provider", id, adding }); };
  const custom = () => { setDraft(emptyCustomProviderDraft()); setError(""); setStep({ kind: "custom" }); };
  async function save() {
    if (busy) return;
    setSubmitting(true); setError("");
    try {
      if (step.kind === "custom") {
        const result = await props.onCreateCustomProvider(draft);
        if (!result) return;
        if (result.created_provider) props.onProviderAdded?.(result.created_provider);
        lastProvider.current = result.created_provider ?? null;
        returnToOrigin();
      } else if (step.kind === "provider" && await props.onSaveProvider(step.id)) {
        if (provider?.auth_type === "oauth" && !provider.configured) return;
        if (step.adding) props.onProviderAdded?.(step.id);
        returnToOrigin();
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSubmitting(false); }
  }
  useEffect(() => {
    if (step.kind !== "provider" || !step.adding || provider?.auth_type !== "oauth" || !provider.configured || busy || !props.onProviderAdded) return;
    props.onProviderAdded(step.id); props.onResetProviderDraft(step.id); props.onClose();

  }, [step, provider?.auth_type, provider?.configured, busy, props.onProviderAdded, props.onResetProviderDraft, props.onClose]);
  return { step, query, setQuery, draft, setDraft, error, busy, provider, lastProvider, close, back, edit, custom, save,
    customSaving: props.providerSaving === CUSTOM_PROVIDER_CREATION_KEY || submitting,
    cancel: () => { reset(); returnToOrigin(); },
    choose: () => setStep({ kind: "picker" }),
    canGoBack: props.entry.origin === "providers" || step.kind === "custom" || step.kind === "provider" && (step.adding || props.entry.kind === "manage") || step.kind === "picker" && props.entry.kind === "manage",
    configured: props.settings.providers.filter(row => row.configured),
    available: props.settings.providers.filter(row => !row.configured && row.id !== "custom"),
  };
}
export type ProviderSetup = ReturnType<typeof useProviderSetup>;
