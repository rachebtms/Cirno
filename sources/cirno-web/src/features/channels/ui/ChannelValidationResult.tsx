import { Spinner } from "@heroui/react";
import { Check, CircleAlert, ExternalLink, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { channelValidationMessage } from "@/features/channels/model/validationMessages";
import type {
  ChannelValidationPayload,
  CirnoFeatureInfo,
} from "@/lib/contracts/channels";
const icons = { pass: Check, fail: X, warn: CircleAlert };
export function ChannelValidationResult({
  validation,
  validating,
  feature,
}: {
  validation: ChannelValidationPayload | null;
  validating: boolean;
  feature: CirnoFeatureInfo;
}) {
  const { t } = useTranslation();
  if (!validation && !validating) return null;
  return (
    <section
      role="status"
      aria-live="polite"
      aria-busy={validating}
      className="channel-validation"
    >
      {validating ? (
        <p>
          <Spinner size="sm" />
          {t("settings.channels.checking")}
        </p>
      ) : (
        validation && (
          <>
            <header>
              <strong>
                {validation.identity?.name ?? feature.display_name}
              </strong>
              <span>
                {t(`settings.channels.validation.${validation.status}`, {
                  defaultValue: validation.status,
                })}
              </span>
            </header>
            {validation.identity?.workspace && (
              <p>{validation.identity.workspace}</p>
            )}
            <ul>
              {validation.checks.map((check) => {
                const Icon =
                  icons[check.status as keyof typeof icons] ?? CircleAlert;
                return (
                  <li key={check.id} data-status={check.status}>
                    <Icon size={16} />
                    <div>
                      <strong>
                        {channelValidationMessage(check.label, t)}
                      </strong>
                      {check.message && (
                        <p>{channelValidationMessage(check.message, t)}</p>
                      )}
                      {check.action_url && (
                        <a
                          href={check.action_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {t("settings.channels.open")}
                          <ExternalLink size={14} />
                        </a>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )
      )}
    </section>
  );
}
