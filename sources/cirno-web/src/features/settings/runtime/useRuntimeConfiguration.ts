import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { RUNTIME_CONFIG_FIELDS, type RuntimeConfigField } from "../system/runtime-config-fields";
import { updateRuntimeConfigSettings } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import type { RuntimeConfigValue, SettingsPayload } from "@/lib/contracts/settings";
import type { ApplySettingsPayload } from "../contracts";
import { useLifetime } from "@/ui/resources/useLifetime";

type Draft = string | boolean;

function displayValue(value: RuntimeConfigValue | undefined): Draft {
  if (typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.join("\n");
  return value == null ? "" : String(value);
}

export function useRuntimeConfigSettings(
  settings: SettingsPayload | null,
  client: CirnoClient,
  applyPayload: ApplySettingsPayload,
) {
  const { t } = useTranslation();
  const isCurrent = useLifetime(client);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const current = useRef({ settings, drafts });
  current.current = { settings, drafts };
  const updateDrafts = (update: (drafts: Record<string, Draft>) => Record<string, Draft>) => {
    current.current.drafts = update(current.current.drafts);
    setDrafts(current.current.drafts);
  };
  const lastFailure = useRef("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [invalidField, setInvalidField] = useState<string | null>(null);
  const delay = useRef(600);
  const saveLatest = useRef<(group: string) => Promise<boolean>>(async () => true);
  const pendingGroups = useRef<string[]>([]);
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  useEffect(() => {
    setDrafts({}); setErrors({}); setSaved({}); setSaving(null); setInvalidField(null);
    return () => { inFlight.current = null; };
  }, [client]);
  useEffect(() => {
    if (invalidField && saving === null) document.getElementById(`runtime-${invalidField}`)?.focus();
  }, [invalidField, saving]);
  const value = (path: string): Draft => current.current.drafts[path] ?? displayValue(current.current.settings?.runtime_config?.[path]);
  const visible = (field: RuntimeConfigField) => (!field.path.includes(".memory.embedding_") || field.path.endsWith(".embedding_enabled") || value("agents.defaults.memory.embedding_enabled") === true) && (!field.when || (Array.isArray(field.when.value)
    ? field.when.value.includes(String(value(field.when.path)))
    : value(field.when.path) === field.when.value));
  const dirty = (field: RuntimeConfigField) =>
    current.current.drafts[field.path] !== undefined && current.current.drafts[field.path] !== displayValue(current.current.settings?.runtime_config?.[field.path]);
  const discard = (group: string) => {
    updateDrafts((prev) => Object.fromEntries(Object.entries(prev).filter(([path]) =>
      !RUNTIME_CONFIG_FIELDS.some((field) => field.group === group && field.path === path),
    )));
    setErrors((prev) => ({ ...prev, [group]: "" }));
    setInvalidField(null);
  };
  const change = (field: RuntimeConfigField, next: Draft) => {
    delay.current = ["boolean", "toggle", "select", "preset"].includes(field.kind) ? 0 : 600;
    updateDrafts((prev) => ({ ...prev, [field.path]: next }));
    setSaved((prev) => ({ ...prev, [field.group]: false }));
    setErrors((prev) => ({ ...prev, [field.group]: "" }));
    setInvalidField(null);
  };
  const reject = (field: RuntimeConfigField, message: string) => {
    setSaved((prev) => ({ ...prev, [field.group]: false }));
    setErrors((prev) => ({ ...prev, [field.group]: message }));
    setInvalidField(field.path);
  };
  const save = async (group: string) => {
    if (!isCurrent()) return false;
    if (inFlight.current) {
      await inFlight.current;
      if (!isCurrent()) return false;
      return saveLatest.current(group);
    }
    const settings = current.current.settings;
    if (!settings?.runtime_config) return true;
    const editedValue = (field: RuntimeConfigField) => value(field.path);
    const changed = RUNTIME_CONFIG_FIELDS.filter((field) => field.group === group && visible(field)
      && editedValue(field) !== displayValue(settings.runtime_config?.[field.path]));
    if (!changed.length) return true;
    const submitted = Object.fromEntries(changed.map(field => [field.path, editedValue(field)]));
    const values: Record<string, RuntimeConfigValue> = {};
    for (const field of changed) {
      const raw = submitted[field.path];
      if (field.kind === "idle-compaction") {
        if (!/^\d+$/.test(String(raw)) || !Number.isSafeInteger(Number(raw))) {
          reject(field, t("settings.runtimeConfig.idleCompaction.numberError"));
          return false;
        }
        values[field.path] = Number(raw);
      } else if (field.kind === "number" || field.kind === "duration") {
        const maximum = field.kind === "duration" ? settings.advanced.exec_max_runtime_limit || undefined : field.max;
        const parsed = Number(raw);
        if (String(raw).trim() === "" || !Number.isFinite(parsed)
          || (field.step !== "any" && !Number.isSafeInteger(parsed))
          || (field.min !== undefined && parsed < field.min)
          || (maximum !== undefined && parsed > maximum)) {
          setErrors((prev) => ({ ...prev, [group]: t("settings.runtimeConfig.numberError") }));
          setInvalidField(field.path);
          return false;
        }
        values[field.path] = parsed;
      } else if (field.kind === "list") {
        values[field.path] = String(raw).split("\n").map((line) => line.trim()).filter(Boolean);
      } else if (field.kind === "nullable" || field.kind === "preset") {
        values[field.path] = String(raw).trim() || null;
      } else {
        values[field.path] = raw;
      }
    }
    setSaving(group);
    setErrors((prev) => ({ ...prev, [group]: "" }));
    const request = (async () => {
      try {
        const payload = await updateRuntimeConfigSettings(client, values);
        if (!isCurrent()) return false;
        current.current.settings = payload;
        applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true });
        // A response acknowledges only the submitted values, not edits made while it was in flight.
        updateDrafts(current => Object.fromEntries(Object.entries(current).filter(([path, raw]) =>
          submitted[path] !== raw,
        )));
        setInvalidField(null);
        setSaved((prev) => ({ ...prev, [group]: true }));
        return true;
      } catch (error) {
        if (!isCurrent()) return false;
        const message = error instanceof Error ? error.message : String(error);
        lastFailure.current = message;
        setErrors((prev) => ({ ...prev, [group]: message }));
        setInvalidField(changed.find((field) => message.startsWith(field.path))?.path ?? null);
        return false;
      } finally { if (isCurrent()) setSaving(null); }
    })();
    inFlight.current = request;
    try { return await request; }
    finally { if (inFlight.current === request) inFlight.current = null; }
  };
  saveLatest.current = save;
  pendingGroups.current = [...new Set(RUNTIME_CONFIG_FIELDS.filter((field) =>
    visible(field) && dirty(field) && !errors[field.group]
      && !RUNTIME_CONFIG_FIELDS.some((other) => other.group === field.group && other.saveOnBlur && dirty(other)),
  ).map((field) => field.group))];
  useEffect(() => {
    if (saving) return;
    const timer = window.setTimeout(() => {
      const group = pendingGroups.current[0];
      if (group) void saveLatest.current(group);
    }, delay.current);
    return () => window.clearTimeout(timer);
  }, [drafts, saving]);
  const commit = (field: RuntimeConfigField, next: Draft) => {
    if (next === value(field.path) && !dirty(field)) return;
    change(field, next);
    void save(field.group);
  };
  const saveProxy = async (next: string) => {
    const field = RUNTIME_CONFIG_FIELDS.find(field => field.path === "network.proxy")!;
    change(field, next.trim());
    if (!await saveLatest.current(field.group)) throw new Error(lastFailure.current);
  };
  const completion = {
    needsCompletion: () => !!inFlight.current || RUNTIME_CONFIG_FIELDS.some(field => visible(field) && dirty(field)),
    commit: async (): Promise<boolean> => {
      while (true) {
        if (!isCurrent()) return false;
        if (inFlight.current && !await inFlight.current) return false;
        const groups = [...new Set(RUNTIME_CONFIG_FIELDS.filter(field => visible(field) && dirty(field)).map(field => field.group))];
        if (!groups.length) return true;
        for (const group of groups) if (!await saveLatest.current(group)) return false;
      }
    },
  };
  return { value, visible, dirty, discard, change, commit, reject, save, saveProxy, completion, saving, errors, invalidField, saved };
}

export type RuntimeConfigController = ReturnType<typeof useRuntimeConfigSettings>;
