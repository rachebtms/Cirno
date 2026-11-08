import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  modelPresetOptionsFromSettings,
  toModelBadgeInfo,
} from "@/components/thread/model-preset";
import {
  fetchSettings
} from "@/lib/api";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { useClient } from "@/providers/ClientProvider";

interface ThreadModelsOptions {
  session: ChatSummary | null;
  settingsSnapshot: SettingsPayload | null;
  settingsLoading: boolean;
}

export function useThreadModels({ session, settingsSnapshot, settingsLoading }: ThreadModelsOptions) {
  const { client, getToken, modelName } = useClient();
  const { t } = useTranslation();
  const chatId = session?.chatId ?? null;
  const [settings, setSettings] = useState<SettingsPayload | null>(settingsSnapshot);
  const [modelSettingsError, setModelSettingsError] = useState("");
  const settingsOwner = useRef({ snapshot: settingsSnapshot, getToken, revision: 0 });
  if (settingsOwner.current.snapshot !== settingsSnapshot || settingsOwner.current.getToken !== getToken) {
    settingsOwner.current = { snapshot: settingsSnapshot, getToken, revision: 0 };
  }
  const [modelFallback, setModelFallback] = useState<{
    chatId: string;
    model: string;
    reauthProvider?: string;
    dismissed: boolean;
  } | null>(null);
  const sessionModelPreset = session?.modelPreset?.trim() || null;
  const [localModelPreset, setLocalModelPreset] = useState<string | null>(null);
  const [modelPresetError, setModelPresetError] = useState("");
  const modelPresetGeneration = useRef(0);
  useEffect(() => {
    modelPresetGeneration.current += 1;
    setLocalModelPreset(null);
    setModelPresetError("");
  }, [session?.key, sessionModelPreset]);
  const configuredPresetNames = useMemo(
    () => new Set(settings?.model_presets.map((preset) => preset.id) ?? []),
    [settings],
  );
  const activeModelPreset = (
    (localModelPreset && (!settings || configuredPresetNames.has(localModelPreset))
      ? localModelPreset
      : null)
    || (sessionModelPreset && (!settings || configuredPresetNames.has(sessionModelPreset))
      ? sessionModelPreset
      : null)
    || settings?.agent.model_preset
    || "default"
  );
  useEffect(() => {
    setModelFallback(null);
    if (!chatId) return;
    return client.onChat(chatId, (event) => {
      if (event.event !== "turn_model_updated") return;
      if (event.fallback !== true) {
        // The next turn starts with its configured model, not the previous fallback.
        setModelFallback(null);
        return;
      }
      const model = event.model_name.trim();
      if (!model) return;
      const reauthProvider = typeof event.reauth_provider === "string"
        ? event.reauth_provider.trim() || undefined : undefined;
      // A tool loop may report the same fallback repeatedly. Closing the notice
      // lasts until the next turn/model change, without changing the actual preset.
      setModelFallback((current) => {
        if (current?.chatId === chatId && current.model === model) {
          // An explicit auth rejection is actionable even after dismissing a
          // generic fallback. A circuit-skipped call must not erase that reason.
          return reauthProvider && reauthProvider !== current.reauthProvider
            ? { ...current, reauthProvider, dismissed: false } : current;
        }
        return { chatId, model, reauthProvider, dismissed: false };
      });
    });
  }, [activeModelPreset, chatId, client]);
  const handleModelPresetChange = useCallback((name: string) => {
    const generation = ++modelPresetGeneration.current;
    setModelPresetError("");
    if (!chatId) { setLocalModelPreset(name); return; }
    void client.sendSystemCommand(chatId, `/model ${name}`).then(() => {
      if (modelPresetGeneration.current === generation) setLocalModelPreset(name);
    }).catch((error: unknown) => {
      if (modelPresetGeneration.current === generation) setModelPresetError(error instanceof Error ? error.message : String(error));
    });
  }, [chatId, client]);
  const modelPresetOptions = useMemo(
    () => modelPresetOptionsFromSettings(settings),
    [settings],
  );
  const modelBadge = useMemo(
    () => toModelBadgeInfo(modelName, settings, activeModelPreset),
    [activeModelPreset, modelName, settings],
  );
  const modelBadgeLabel = modelBadge.needsSetup
    ? t("thread.composer.chooseAI", { defaultValue: "Choose your AI" })
    : modelBadge.label;
  const refreshModelSettings = useCallback(async () => {
    const owner = settingsOwner.current;
    const revision = ++owner.revision;
    try {
      const payload = await fetchSettings(getToken());
      if (settingsOwner.current === owner && owner.revision === revision) {
        setSettings(payload);
        setModelSettingsError("");
      }
    } catch (reason) {
      if (settingsOwner.current === owner && owner.revision === revision) {
        setModelSettingsError(reason instanceof Error ? reason.message : String(reason));
      }
    }
  }, [getToken, settingsSnapshot]);

  useEffect(() => {
    if (settingsSnapshot) {
      setSettings(settingsSnapshot);
      setModelSettingsError("");
      return;
    }
    if (!settingsLoading) void refreshModelSettings();
  }, [refreshModelSettings, settingsLoading, settingsSnapshot]);

  useEffect(() => {
    return client.onRuntimeModelUpdate(() => {
      void refreshModelSettings();
    });
  }, [client, refreshModelSettings]);

  return {
    settings, modelSettingsError, modelFallback, setModelFallback, modelPresetError, localModelPreset,
    activeModelPreset, handleModelPresetChange, modelPresetOptions, modelBadge, modelBadgeLabel,
  };
}
