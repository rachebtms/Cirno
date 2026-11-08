import { Alert, Button, Description, Form, Label, TextArea, TextField } from "@heroui/react";
import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AppsCatalogProps } from "../model/contracts";
import { mcpOAuthStatusText } from "../model/status";

export function McpAuthorization({ options }: { options: AppsCatalogProps }) {
  const { t } = useTranslation();
  const flow = options.mcpOAuthFlow;
  if (!flow?.authorization_url) return null;
  if (flow.completion_input === "callback_url") return <Form validationBehavior="aria" className="catalog-authorization" onSubmit={event => { event.preventDefault(); options.onMcpOAuthComplete(); }}>
    <TextField value={options.mcpOAuthCallbackUrl} onChange={options.onMcpOAuthCallbackUrlChange} isRequired isDisabled={options.mcpOAuthCompleting} isInvalid={Boolean(options.mcpOAuthCallbackError)}>
      <Label>{t("settings.oauth.callbackUrl")}</Label><Description>{t("settings.mcp.manualCallbackHelp")}</Description>
      <TextArea placeholder={t("settings.oauth.callbackUrlPlaceholder")} autoComplete="off" spellCheck={false} rows={3} />
    </TextField>
    {options.mcpOAuthCallbackError && <Alert status="danger" role="alert"><Alert.Description>{options.mcpOAuthCallbackError}</Alert.Description></Alert>}
    <div className="catalog-actions"><Button variant="secondary" onPress={options.onMcpOAuthOpen}>{t("settings.mcp.continueSignIn")}<ExternalLink size={16} /></Button>
      <Button type="submit" isPending={options.mcpOAuthCompleting}>{t("settings.oauth.finishSignIn")}</Button></div>
  </Form>;
  return options.mcpOAuthPopupBlocked ? <div className="catalog-authorization"><p>{mcpOAuthStatusText(flow.status, true, (key, fallback) => t(key, { defaultValue: fallback }), flow.completion_input)}</p>
    <Button variant="secondary" onPress={options.onMcpOAuthOpen}>{t("settings.mcp.continueSignIn")}<ExternalLink size={16} /></Button></div> : null;
}
