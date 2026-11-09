import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { RUNTIME_CONFIG_FIELDS, type RuntimeConfigField } from "../system/runtime-config-fields";
import { updateRuntimeConfigSettings } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import type { RuntimeConfigValue, SettingsPayload } from "@/lib/contracts/settings";
import type { ApplySettingsPayload } from "../contracts";

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
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const inFlight = useRef(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [invalidField, setInvalidField] = useState<string | null>(null);
  const delay = useRef(600);
  const saveLatest = useRef<(group: string) => Promise<void>>(async () => {});
  const pendingGroups = useRef<string[]>([]);
  const queuedSaves = useRef<string[]>([]);
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (invalidField && saving === null) document.getElementById(`runtime-${invalidField}`)?.focus();
  }, [invalidField, saving]);
  const value = (path: string): Draft => drafts[path] ?? displayValue(settings?.runtime_config?.[path]);
  const visible = (field: RuntimeConfigField) => (!field.path.includes(".memory.embedding_") || field.path.endsWith(".embedding_enabled") || value("agents.defaults.memory.embedding_enabled") === true) && (!field.when || (Array.isArray(field.when.value)
    ? field.when.value.includes(String(value(field.when.path)))
    : value(field.when.path) === field.when.value));
  const dirty = (field: RuntimeConfigField) =>
    drafts[field.path] !== undefined && drafts[field.path] !== displayValue(settings?.runtime_config?.[field.path]);
  const discard = (group: string) => {
    setDrafts((prev) => Object.fromEntries(Object.entries(prev).filter(([path]) =>
      !RUNTIME_CONFIG_FIELDS.some((field) => field.group === group && field.path === path),
    )));
    setErrors((prev) => ({ ...prev, [group]: "" }));
    setInvalidField(null);
  };
  const change = (field: RuntimeConfigField, next: Draft) => {
    delay.current = ["boolean", "toggle", "select", "preset"].includes(field.kind) ? 0 : 600;
    setDrafts((prev) => ({ ...prev, [field.path]: next }));
    setSaved((prev) => ({ ...prev, [field.group]: false }));
    setErrors((prev) => ({ ...prev, [field.group]: "" }));
    setInvalidField(null);
  };
  const reject = (field: RuntimeConfigField, message: string) => {
    setSaved((prev) => ({ ...prev, [field.group]: false }));
    setErrors((prev) => ({ ...prev, [field.group]: message }));
    setInvalidField(field.path);
  };
  const save = async (group: string, edits: Record<string, Draft> = {}) => {
    if (!settings?.runtime_config) return;
    if (inFlight.current) {
      if (!queuedSaves.current.includes(group)) queuedSaves.current.push(group);
      return;
    }
    const editedValue = (field: RuntimeConfigField) => edits[field.path] ?? value(field.path);
    const changed = RUNTIME_CONFIG_FIELDS.filter((field) => field.group === group && visible(field)
      && editedValue(field) !== displayValue(settings.runtime_config?.[field.path]));
    if (!changed.length) return;
    const values: Record<string, RuntimeConfigValue> = {};
    for (const field of changed) {
      const raw = editedValue(field);
      if (field.kind === "idle-compaction") {
        if (!/^\d+$/.test(String(raw)) || !Number.isSafeInteger(Number(raw))) {
          reject(field, t("settings.runtimeConfig.idleCompaction.numberError"));
          return;
        }
        values[field.path] = Number(raw);
      } else if (field.kind === "number" || field.kind === "duration") {
        const maximum = field.kind === "duration" ? settings.advanced.exec_max_runtime_limit || undefined : field.max;
        const parsed = Number(raw);
        if (String(raw).trim() === "" || !Number.isFinite(parsed)
          || !Number.isInteger(parsed)
          || (field.min !== undefined && parsed < field.min)
          || (maximum !== undefined && parsed > maximum)) {
          setErrors((prev) => ({ ...prev, [group]: t("settings.runtimeConfig.numberError") }));
          setInvalidField(field.path);
          return;
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
    inFlight.current = true;
    setSaving(group);
    setErrors((prev) => ({ ...prev, [group]: "" }));
    try {
      const payload = await updateRuntimeConfigSettings(client, values);
      applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true });
      // A response acknowledges only the submitted values, not edits made while it was in flight.
      setDrafts(current => Object.fromEntries(Object.entries(current).filter(([path, raw]) =>
        !changed.some(field => field.path === path && editedValue(field) === raw),
      )));
      setInvalidField(null);
      setSaved((prev) => ({ ...prev, [group]: true }));
    } catch (error) {
      const message = (error as Error).message;
      setErrors((prev) => ({ ...prev, [group]: message }));
      setInvalidField(changed.find((field) => message.startsWith(field.path))?.path ?? null);
    } finally {
      inFlight.current = false;
      setSaving(null);
    }
  };
  saveLatest.current = save;
  pendingGroups.current = [...new Set(RUNTIME_CONFIG_FIELDS.filter((field) =>
    visible(field) && dirty(field) && !errors[field.group]
      && !RUNTIME_CONFIG_FIELDS.some((other) => other.group === field.group && other.saveOnBlur && dirty(other)),
  ).map((field) => field.group))];
  useEffect(() => {
    if (saving) return;
    const timer = window.setTimeout(() => {
      const group = queuedSaves.current.shift() ?? pendingGroups.current[0];
      if (group) void saveLatest.current(group);
    }, delay.current);
    return () => window.clearTimeout(timer);
  }, [drafts, saving]);
  const saveText = async (field: RuntimeConfigField, next: string) => {
    const payload = await updateRuntimeConfigSettings(client, {
      [field.path]: field.kind === "list" ? next.split("\n").map((line) => line.trim()).filter(Boolean) : next,
    });
    applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true });
    setSaved((prev) => ({ ...prev, [field.group]: true }));
  };
  const commit = (field: RuntimeConfigField, next: Draft) => {
    if (next === value(field.path) && !dirty(field)) return;
    change(field, next);
    void save(field.group, { [field.path]: next });
  };
  const saveProxy = async (next: string) => {
    setSaving("proxy");
    try {
      const payload = await updateRuntimeConfigSettings(client, { "network.proxy": next.trim() || null });
      applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true });
      discard("proxy");
      setSaved((prev) => ({ ...prev, proxy: true }));
    } finally {
      setSaving(null);
    }
  };
  return { value, visible, dirty, discard, change, commit, reject, save, saveText, saveProxy, saving, errors, invalidField, saved };
}

export type RuntimeConfigController = ReturnType<typeof useRuntimeConfigSettings>;
