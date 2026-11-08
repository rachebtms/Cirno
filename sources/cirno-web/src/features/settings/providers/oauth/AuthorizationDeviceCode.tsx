import { Alert, Button, Input, Label, TextField } from "@heroui/react";
import { Clipboard } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { ProviderOAuthAuthorizationRequired } from "@/lib/contracts/models";
import { useLifetime } from "@/ui/resources/useLifetime";

export function AuthorizationDeviceCode({ flow }: { flow: ProviderOAuthAuthorizationRequired }) {
  const { t } = useTranslation(),
    isCurrent = useLifetime(flow);
  const [feedback, setFeedback] = useState<{ flow: typeof flow; copied: boolean } | null>(null);
  const copied = feedback?.flow === flow && feedback.copied;
  const failed = feedback?.flow === flow && !feedback.copied;
  const copy = async () => {
    const result = await copyTextToClipboard(flow.user_code ?? "");
    if (isCurrent()) setFeedback({ flow, copied: result });
  };
  return (
    <>
      <TextField isReadOnly value={flow.user_code ?? ""}>
        <Label>{t("settings.oauth.deviceCode")}</Label>
        <Input className="provider-device-code" onFocus={(event) => event.target.select()} />
      </TextField>
      <Button variant="secondary" isDisabled={!flow.user_code} onPress={() => void copy()}>
        <Clipboard size={16} />
        {t(copied ? "code.copied" : "code.copy")}
      </Button>
      {failed && (
        <Alert status="danger" role="alert">
          <Alert.Description>{t("common.copyFailed")}</Alert.Description>
        </Alert>
      )}
    </>
  );
}
