import { Accordion, Description, Input, Label, TextField } from "@heroui/react";
import { useState, type ComponentProps, type ReactNode, type Ref } from "react";
import { useTranslation } from "react-i18next";
import { changeProxyAddress, changeProxyAuthentication, isProxyUrlReference, splitProxyUrl } from "@/lib/proxy-url";
import "./proxy.css";

type AddressProps = Pick<ComponentProps<typeof Input>, "id" | "aria-describedby" | "aria-invalid">;
export function SharedProxyEditor({ value, onChange, disabled, inputRef, addressProps, description, stackCredentials = false }: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  inputRef?: Ref<HTMLInputElement>;
  addressProps?: AddressProps;
  description?: ReactNode;
  stackCredentials?: boolean;
}) {
  const { t } = useTranslation();
  const parts = splitProxyUrl(value);
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const open = expanded ?? parts.userinfo !== null;
  const reference = isProxyUrlReference(parts.address);
  const credentialsDisabled = disabled || !parts.address.trim() || reference;
  return <div data-shared-proxy-editor className="proxy-editor">
    <TextField autoFocus={Boolean(inputRef)} value={parts.address} isDisabled={disabled} isInvalid={Boolean(addressProps?.["aria-invalid"])}
      onChange={next => onChange(changeProxyAddress(value, next))}>
      <Label>{t("settings.runtimeConfig.fields.network_proxy.label")}</Label>
      {description && <Description>{description}</Description>}
      <Input {...addressProps} ref={inputRef} autoComplete="off" spellCheck={false} placeholder="http://127.0.0.1:7890" />
    </TextField>
    <Accordion expandedKeys={open ? ["authentication"] : []} onExpandedChange={keys => setExpanded(keys.has("authentication"))}>
      <Accordion.Item id="authentication"><Accordion.Heading><Accordion.Trigger>
        {t("settings.network.authentication")}<Accordion.Indicator />
      </Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body>
        {reference ? <p className="proxy-help">{t("settings.network.proxyReferenceAuth")}</p> : <div className="proxy-credentials" data-stacked={stackCredentials || undefined}>
          <TextField value={parts.username} isDisabled={credentialsDisabled}
            onChange={next => { setExpanded(true); onChange(changeProxyAuthentication(value, next, parts.password)); }}>
            <Label>{t("settings.network.username")}</Label><Input autoComplete="off" spellCheck={false} />
          </TextField>
          <TextField value={parts.password} isDisabled={credentialsDisabled}
            onChange={next => { setExpanded(true); onChange(changeProxyAuthentication(value, parts.username, next)); }}>
            <Label>{t("settings.network.password")}</Label><Input type="password" autoComplete="new-password" />
          </TextField>
        </div>}
      </Accordion.Body></Accordion.Panel></Accordion.Item>
    </Accordion>
  </div>;
}
