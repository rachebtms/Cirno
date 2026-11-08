import { Alert, Button, Description } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { ProviderRow, ProviderSettingsProps } from "../model/contracts";
export function ProviderOAuthFields({ provider, options, dirty, disabled }: {
  provider: ProviderRow; options: ProviderSettingsProps; dirty: boolean; disabled: boolean;
}) {
  const { t } = useTranslation();
  const remoteHelp = { openai_codex: "settings.oauth.codexRemoteSignInHelp", xai_grok: "settings.oauth.remoteSignInHelp" };
  const help = options.remoteBrowserAccess ? remoteHelp[provider.id as keyof typeof remoteHelp] : undefined;
  return <div className="provider-fields">
    {provider.oauth_error && <Alert status="danger" role="alert"><Alert.Description>{provider.oauth_error}</Alert.Description></Alert>}
    <Description>{t(provider.configured ? "settings.oauth.signedIn" : help ?? "settings.oauth.signInHelp")}</Description>
    <div className="provider-actions">
      {provider.configured && <Button variant="secondary" isDisabled={disabled} onPress={() => options.onProviderOAuthLogout(provider.id)}>{t("settings.oauth.signOut")}</Button>}
      <Button isPending={disabled && options.providerOperation?.action === "login"} isDisabled={disabled || dirty || !provider.oauth_login_supported}
        onPress={() => options.onProviderOAuthLogin(provider.id)}>{t(provider.configured ? "settings.oauth.signInAgain" : "settings.oauth.signIn")}</Button>
    </div>
    {dirty && <Description>{t("settings.providers.saveAdvancedBeforeSignIn")}</Description>}
  </div>;
}
