import { Button, Card } from "@heroui/react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WebUIMutationTransport } from "@/lib/api";
import { InlineError } from "@/ui/feedback/InlineError";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import { SettingsTextEditor } from "@/features/settings/shared/SettingsTextEditor";
import { useProfileFile } from "./model/useProfileFile";
import "./profile.css";

const FILE_GROUPS = {
  memory: ["memory"],
  personality: ["soul", "worker", "user", "instructions"],
  heartbeat: ["heartbeat"],
} as const;
function ProfileFileCard({ client, name }: { client: WebUIMutationTransport; name: string }) {
  const { t } = useTranslation();
  const state = useProfileFile(client, name),
    title = t(`settings.homeFiles.${name}`);
  return (
    <Card className="profile-file">
      <Card.Header>
        <div>
          <h3>{title}</h3>
          {state.value && <p className="profile-file-path">{state.value.file}</p>}
        </div>
        <div className="profile-file-actions">
          <Button
            variant="ghost"
            size="sm"
            isIconOnly
            isDisabled={state.loading}
            aria-label={`${t("settings.homeFiles.reload")} ${title}`}
            onPress={() => {
              void state.refresh();
            }}
          >
            <RefreshCw size={16} />
          </Button>
          {state.value && (
            <SettingsTextEditor
              title={title}
              description={state.value.file}
              value={state.value.content}
              buttonLabel={`${t("settings.actions.edit")} ${title}`}
              loadValue={state.loadForEdit}
              onSave={state.save}
            />
          )}
        </div>
      </Card.Header>
      {state.error && (
        <Card.Content>
          <InlineError message={state.error} />
        </Card.Content>
      )}
      {state.loading && !state.value && (
        <Card.Content>
          <SkeletonStatus label={t("settings.loading")} className="profile-file-loading">
            <div className="profile-file-placeholder" />
          </SkeletonStatus>
        </Card.Content>
      )}
    </Card>
  );
}
export function ProfileFiles({
  client,
  section,
}: {
  client: WebUIMutationTransport;
  section: keyof typeof FILE_GROUPS;
}) {
  const { t } = useTranslation();
  return (
    <section className="profile-files">
      <h2>{t("settings.homeFiles.title")}</h2>
      {FILE_GROUPS[section].map((name) => (
        <ProfileFileCard key={name} client={client} name={name} />
      ))}
    </section>
  );
}
