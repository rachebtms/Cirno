import {
  Alert,
  Button,
  Description,
  Form,
  Input,
  Label,
  Modal,
  Spinner,
  TextArea,
  TextField,
} from "@heroui/react";
import { useCallback, useRef } from "react";
import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ProviderOAuthAuthorizationRequired } from "@/lib/contracts/models";
import { AuthorizationDeviceCode } from "./oauth/AuthorizationDeviceCode";
import "./providers.css";

type AuthorizationDialogProps = {
  flow: ProviderOAuthAuthorizationRequired | null;
  providerLabel: string;
  authorizationResponse: string;
  completing: boolean;
  cancelling: boolean;
  canComplete: boolean;
  error: string | null;
  remoteBrowserAccess: boolean;
  onAuthorizationResponseChange: (value: string) => void;
  onOpenAuthorization: () => void;
  onComplete: () => void;
  onRetry: () => void;
  onClose: () => void;
};

export function ProviderOAuthLoginDialog(props: AuthorizationDialogProps) {
  const visible = useRef<AuthorizationDialogProps | null>(null);
  if (props.flow) visible.current = props;
  const release = useCallback((element: HTMLElement | null) => {
    if (!element) visible.current = null;
  }, []);
  const {
    flow,
    providerLabel,
    authorizationResponse,
    completing,
    cancelling,
    canComplete,
    error,
    remoteBrowserAccess,
  } = visible.current ?? props;
  const { onAuthorizationResponseChange, onOpenAuthorization, onComplete, onRetry, onClose } =
    props;

  const { t } = useTranslation();
  const callback = flow?.completion_input === "callback_url",
    device = flow?.completion_input === "device_code";
  const help = device
    ? "deviceCodeHelp"
    : callback
      ? remoteBrowserAccess
        ? "remoteCallbackHelp"
        : "localCallbackHelp"
      : remoteBrowserAccess
        ? "remoteCodeHelp"
        : "localCodeHelp";
  const waiting = device
    ? "waitingForDeviceApproval"
    : callback && remoteBrowserAccess
      ? "pasteCallbackToContinue"
      : "waitingForCallback";
  return (
    <Modal.Backdrop
      isOpen={Boolean(props.flow)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      isDismissable={!cancelling}
      isKeyboardDismissDisabled={cancelling}
    >
      <Modal.Container size="sm">
        <Modal.Dialog className="provider-setup-dialog">
          <Modal.Header>
            <Modal.Heading>
              {t("settings.oauth.signIn")} · {providerLabel}
            </Modal.Heading>
            <Modal.CloseTrigger aria-label={t("common.close")} isDisabled={cancelling} />
          </Modal.Header>
          <Form
            ref={release}
            className="provider-form"
            onSubmit={(event) => {
              event.preventDefault();
              onComplete();
            }}
          >
            <Modal.Body className="provider-fields">
              <Description>{t(`settings.oauth.${help}`)}</Description>
              {(!error || cancelling) && (
                <p role="status" className="provider-oauth-wait">
                  <Spinner size="sm" />
                  {t(`settings.oauth.${cancelling ? "cancelling" : waiting}`)}
                </p>
              )}
              {device && flow ? (
                <AuthorizationDeviceCode flow={flow} />
              ) : (
                <TextField
                  value={authorizationResponse}
                  onChange={onAuthorizationResponseChange}
                  isDisabled={completing || !canComplete}
                >
                  <Label>
                    {t(`settings.oauth.${callback ? "callbackUrl" : "authorizationCode"}`)}
                  </Label>
                  {callback ? (
                    <TextArea
                      rows={4}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder={t("settings.oauth.callbackUrlPlaceholder")}
                    />
                  ) : (
                    <Input autoComplete="off" spellCheck={false} />
                  )}
                </TextField>
              )}
              {error && (
                <Alert status="danger" role="alert">
                  <Alert.Content>
                    {!canComplete && (
                      <Alert.Title>
                        {t("settings.oauth.cancelFailed", { provider: providerLabel })}
                      </Alert.Title>
                    )}
                    <Alert.Description>{error}</Alert.Description>
                    <Button
                      variant="secondary"
                      isDisabled={cancelling || completing}
                      onPress={onRetry}
                    >
                      {t("common.retry")}
                    </Button>
                  </Alert.Content>
                </Alert>
              )}
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" isDisabled={!canComplete} onPress={onOpenAuthorization}>
                <ExternalLink size={16} />
                {t(`settings.oauth.${device ? "openGitHub" : callback ? "openChatGPT" : "signIn"}`)}
              </Button>
              {!device && (
                <Button
                  type="submit"
                  isPending={completing}
                  isDisabled={!canComplete || !authorizationResponse.trim()}
                >
                  {t("settings.oauth.finishSignIn")}
                </Button>
              )}
            </Modal.Footer>
          </Form>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
