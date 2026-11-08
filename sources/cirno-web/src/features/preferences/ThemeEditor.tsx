import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ThemePreview } from "./ThemePreview";
import type { Palette, ThemePair } from "./contracts";
import { contrast } from "./palette";
const colors: (keyof Palette)[] = [
  "background",
  "surface",
  "panel",
  "text",
  "muted",
  "accent",
  "border",
];
export function ThemeEditor({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial: ThemePair;
  saving: boolean;
  onSave: (value: ThemePair) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [theme, setTheme] = useState(() => structuredClone(initial));
  const valid = (["light", "dark"] as const).every((mode) =>
    colors.every((key) => /^#[0-9a-fA-F]{6}$/.test(theme[mode][key])),
  );
  const readable =
    valid &&
    (["light", "dark"] as const).every(
      (mode) =>
        contrast(theme[mode].background, theme[mode].text) >= 4.5 &&
        contrast(theme[mode].panel, theme[mode].text) >= 4.5,
    );
  return (
    <form
      className="space-y-5 rounded-2xl border border-border p-4 @min-[640px]/cirno-tab:p-5"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(theme);
      }}
    >
      <fieldset disabled={saving} className="space-y-5">
        <label className="block space-y-2 text-sm">
          <span>{t("themes.name")}</span>
          <Input
            required
            maxLength={80}
            value={theme.name}
            onChange={(event) =>
              setTheme({ ...theme, name: event.target.value })
            }
          />
        </label>
        {valid && <ThemePreview theme={theme} />}
        <div className="grid gap-5 @min-[640px]/cirno-tab:grid-cols-2">
          {(["light", "dark"] as const).map((mode) => (
            <fieldset key={mode} className="min-w-0 space-y-3">
              <legend className="mb-3 text-sm font-medium">
                {t(`settings.values.${mode}`)}
              </legend>
              {colors.map((key) => (
                <label
                  key={key}
                  className="flex min-w-0 items-center justify-between gap-3 text-sm"
                >
                  <span>{t(`themes.colors.${key}`)}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <input
                      type="color"
                      aria-label={`${t(`settings.values.${mode}`)} ${t(`themes.colors.${key}`)}`}
                      className="h-8 w-8 cursor-pointer rounded border-0 bg-transparent p-0"
                      value={
                        /^#[0-9a-fA-F]{6}$/.test(theme[mode][key])
                          ? theme[mode][key]
                          : "#000000"
                      }
                      onChange={(event) =>
                        setTheme({
                          ...theme,
                          [mode]: { ...theme[mode], [key]: event.target.value },
                        })
                      }
                    />
                    <Input
                      aria-label={`${t(`settings.values.${mode}`)} ${t(`themes.colors.${key}`)} hex`}
                      className="h-8 w-24 font-mono text-xs"
                      pattern="#[0-9a-fA-F]{6}"
                      value={theme[mode][key]}
                      onChange={(event) =>
                        setTheme({
                          ...theme,
                          [mode]: { ...theme[mode], [key]: event.target.value },
                        })
                      }
                    />
                  </span>
                </label>
              ))}
            </fieldset>
          ))}
        </div>
        {valid && !readable && (
          <p className="text-sm text-destructive" role="alert">
            {t("themes.contrast")}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onCancel}>
            {t("files.cancel")}
          </Button>
          <Button disabled={!valid || !readable || !theme.name.trim()}>
            {t("themes.save")}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
