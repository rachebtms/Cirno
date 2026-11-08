import { Alert, Button } from "@heroui/react";
import { Check, Copy, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SkillDetail } from "@/lib/contracts/skills";
import { copyTextToClipboard } from "@/lib/clipboard";
import { InlineError } from "@/ui/feedback/InlineError";
export function SkillRequirements({
  detail,
  busy,
  onRefresh,
}: {
  detail: SkillDetail;
  busy: boolean;
  onRefresh: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState<string | null>(null),
    [error, setError] = useState(false);
  const requirements = detail.requirements;
  if (!requirements || !(requirements.missing_bins.length || requirements.missing_env.length)) return null;
  const copy = async (command: string) => {
    const success = await copyTextToClipboard(command);
    setCopied(success ? command : null);
    setError(!success);
  };
  return (
    <section className="skill-requirements">
      <Alert status="warning">
        <Alert.Content>
          <Alert.Title>{t("settings.skills.setupRequired")}</Alert.Title>
          <Alert.Description>{t("settings.skills.setupDescription")}</Alert.Description>
        </Alert.Content>
      </Alert>
      <dl className="skill-requirements-list">
        {(
          [
            ["missing_bins", "missingCommands"],
            ["missing_env", "missingEnvironment"],
          ] as const
        ).map(
          ([field, label]) =>
            !!requirements[field].length && (
              <div key={field}>
                <dt>{t(`settings.skills.${label}`)}</dt>
                <dd>
                  {requirements[field].map((item) => (
                    <code key={item}>{item}</code>
                  ))}
                </dd>
              </div>
            ),
        )}
      </dl>
      {(detail.install_options ?? []).map((option) => (
        <div className="skill-command" key={`${option.id}:${option.command}`}>
          <code>{option.command}</code>
          <Button
            variant="ghost"
            size="sm"
            isIconOnly
            aria-label={t("settings.skills.copySetupCommand")}
            onPress={() => {
              void copy(option.command);
            }}
          >
            {copied === option.command ? <Check size={16} /> : <Copy size={16} />}
          </Button>
        </div>
      ))}
      <InlineError message={error ? t("settings.skills.copySetupFailed") : null} />
      <Button variant="secondary" size="sm" isDisabled={busy} onPress={onRefresh}>
        <RefreshCw size={15} />
        {t("settings.skills.checkAgain")}
      </Button>
    </section>
  );
}
