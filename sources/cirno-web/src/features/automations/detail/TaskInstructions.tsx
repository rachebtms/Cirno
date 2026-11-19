import { Button } from "@heroui/react";
import { Check, Clipboard } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExpandableText } from "@/components/ui/expandable-text";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import {
  automationTriggerCommand,
  isLocalTriggerAutomation,
} from "../model/status";

export function TaskInstructions({ job }: { job: SessionAutomationJob }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false),
    [copiedText, setCopiedText] = useState<string | null>(null);
  const copyAttempt = useRef(0);
  const id = useId();
  const local = isLocalTriggerAutomation(job);
  const message = local ? automationTriggerCommand(job) : job.payload.message;
  const copied = copiedText === message;
  if (job.protected || !message.trim()) return null;
  const expandable = message.length > 360 || message.split(/\r?\n/).length > 6;
  return (
    <section
      className="automation-instructions"
      data-command={local || undefined}
    >
      {local && (
        <div className="automation-command-heading">
          <span>{t("settings.automations.fields.command")}</span>
          <Button
            variant="ghost"
            size="sm"
            onPress={() => {
              const attempt = ++copyAttempt.current;
              void copyTextToClipboard(message).then((ok) => {
                if (ok && attempt === copyAttempt.current) setCopiedText(message);
              });
            }}
          >
            {copied ? <Check size={14} /> : <Clipboard size={14} />}
            {t(
              copied
                ? "settings.automations.commandCopied"
                : "settings.automations.copyCommand",
            )}
          </Button>
        </div>
      )}
      <ExpandableText
        id={id}
        expanded={expanded || !expandable}
        lines={6}
        className="automation-instructions-text"
      >
        {message}
      </ExpandableText>
      {expandable && (
        <Button
          variant="ghost"
          size="sm"
          aria-expanded={expanded}
          aria-controls={id}
          onPress={() => setExpanded(!expanded)}
        >
          {t(
            expanded
              ? "settings.automations.message.showLess"
              : "settings.automations.message.showMore",
          )}
        </Button>
      )}
    </section>
  );
}
