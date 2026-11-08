import { Button, Description, FieldError, InputGroup, Label, TextField } from "@heroui/react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Ref } from "react";

export function PasswordField({ label, name, value, onChange, disabled, visible, onToggle, help, invalid, inputRef, autoFocus, errorMessage, autoComplete = "current-password" }: {
  label: string; name: string; value: string; onChange: (value: string) => void; disabled: boolean;
  visible: boolean; onToggle: () => void; help?: string; invalid?: boolean; errorMessage?: string; autoFocus?: boolean; inputRef?: Ref<HTMLInputElement>; autoComplete?: "current-password" | "new-password";
}) {
  const { t } = useTranslation();
  return <TextField autoFocus={autoFocus} name={name} value={value} onChange={onChange} isDisabled={disabled} isRequired isInvalid={invalid || Boolean(errorMessage)}>
    <Label>{label}</Label>
    <InputGroup><InputGroup.Input ref={inputRef} type={visible ? "text" : "password"} autoComplete={autoComplete} />
      <InputGroup.Suffix><Button isIconOnly variant="ghost" size="sm" isDisabled={disabled}
        aria-label={t(visible ? "app.auth.hidePassword" : "app.auth.showPassword")} onPress={onToggle}>
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </Button></InputGroup.Suffix>
    </InputGroup>
    {help && <Description>{help}</Description>}
    {errorMessage && <FieldError>{errorMessage}</FieldError>}
  </TextField>;
}
