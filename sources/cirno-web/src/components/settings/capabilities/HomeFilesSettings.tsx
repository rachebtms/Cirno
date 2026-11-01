import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { SettingsTextEditor } from "@/components/settings/shared/SettingsTextEditor";
import { SettingsGroup, SettingsRow, SettingsSectionTitle } from "@/components/settings/shared/SettingsControls";
import type { CirnoClient } from "@/lib/cirno-client";

type HomeFile = { name: string; file: string; content: string; revision: string };
const FILE_GROUPS = {
  memory: ["memory"],
  personality: ["soul", "user", "instructions", "heartbeat"],
} as const;

export function HomeFilesSettings({ client, section }: { client: CirnoClient; section: keyof typeof FILE_GROUPS }) {
  const { t } = useTranslation();
  const [files, setFiles] = useState<HomeFile[]>([]);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFiles([]);
    setError("");
    void Promise.all(FILE_GROUPS[section].map(name => client.requestMutation<HomeFile>("settings.profile.read", { name })))
      .then(result => { if (!cancelled) { setFiles(result); setError(""); } })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [client, refresh, section]);
  return <section>
    <div className="flex items-center justify-between">
      <SettingsSectionTitle className="m-0 p-0">{t(section === "personality" ? "settings.nav.personality" : "settings.homeFiles.title")}</SettingsSectionTitle>
      <Button variant="ghost" size="sm" disabled={loading} onClick={() => setRefresh(value => value + 1)}>
        {t("settings.homeFiles.reload")}
      </Button>
    </div>
    {error ? <p role="alert" className="mb-3 text-sm text-destructive">{error}</p> : null}
    <SettingsGroup>{files.map(file => <SettingsRow inline key={file.name} title={t(`settings.homeFiles.${file.name}`)} description={file.file}>
      <SettingsTextEditor buttonLabel={`${t("settings.actions.edit")} ${t(`settings.homeFiles.${file.name}`)}`} title={t(`settings.homeFiles.${file.name}`)} description={file.file}
        value={file.content} disabled={loading} onSave={async content => {
          const saved = await client.requestMutation<HomeFile>("settings.profile.update", {
            name: file.name, content, revision: file.revision,
          });
          setFiles(current => current.map(item => item.name === saved.name ? saved : item));
        }} />
    </SettingsRow>)}</SettingsGroup>
  </section>;
}
