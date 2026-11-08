import { Button } from "@/components/ui/button";
import {
  usePreferences,
  usePreferenceStatus,
  useThemes,
} from "@/hooks/usePreferences";
import { Check, Palette, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ThemePair } from "./contracts";
import { patchPreferences, SNOW_THEME } from "./store";
import { ThemeEditor } from "./ThemeEditor";
import { ThemePreview } from "./ThemePreview";
export function ThemeSettings() {
  const { t } = useTranslation();
  const preferences = usePreferences(),
    builtins = useThemes(),
    status = usePreferenceStatus();
  const themes = [...builtins, ...preferences.customThemes];
  const selected =
    themes.find((theme) => theme.id === preferences.themeId) ?? SNOW_THEME;
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<ThemePair | null>(null);
  const custom = preferences.customThemes.some(
    (theme) => theme.id === selected.id,
  );
  const save = async (theme: ThemePair) => {
    setSaving(true);
    const saved = await patchPreferences({
      themeId: theme.id,
      customThemes: [
        ...preferences.customThemes.filter((item) => item.id !== theme.id),
        theme,
      ],
    });
    setSaving(false);
    if (saved) setEditing(null);
  };
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <Palette size={17} />
          {t("themes.title")}
        </h2>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            setEditing({
              ...selected,
              id: `custom-${crypto.randomUUID()}`,
              name: t("themes.newName"),
            })
          }
        >
          <Plus size={15} className="mr-1" />
          {t("themes.customize")}
        </Button>
      </div>
      <p className="text-sm leading-6 text-muted-foreground">
        {t("themes.syncHint")}
      </p>
      {status.error && (
        <p role="alert" className="break-words text-sm text-destructive">
          {t("themes.saveFailed")} {status.error}
        </p>
      )}
      <div className="grid gap-3 @min-[640px]/cirno-tab:grid-cols-2">
        {themes.map((theme) => (
          <button
            key={theme.id}
            type="button"
            aria-pressed={selected.id === theme.id}
            className="space-y-2 rounded-xl p-1 text-left outline-offset-4 focus-visible:outline focus-visible:outline-ring"
            onClick={() => patchPreferences({ themeId: theme.id })}
          >
            <ThemePreview theme={theme} />
            <span className="flex items-center justify-between px-1 text-sm">
              <span>{theme.name}</span>
              {selected.id === theme.id && (
                <Check size={15} className="text-primary" />
              )}
            </span>
          </button>
        ))}
      </div>
      {custom && (
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setEditing(selected)}
          >
            <Pencil size={14} className="mr-1" />
            {t("themes.edit")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              patchPreferences({
                themeId: "cirno-snow",
                customThemes: preferences.customThemes.filter(
                  (theme) => theme.id !== selected.id,
                ),
              })
            }
          >
            <Trash2 size={14} className="mr-1" />
            {t("themes.remove")}
          </Button>
        </div>
      )}
      {editing && (
        <ThemeEditor
          key={editing.id}
          saving={saving}
          initial={editing}
          onCancel={() => setEditing(null)}
          onSave={save}
        />
      )}
    </section>
  );
}
