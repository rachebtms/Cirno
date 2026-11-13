import { Button, InputGroup } from "@heroui/react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Reusable masked input; its enclosing TextField owns the value and label. */
export function SecretInput({ visible, onToggle, disabled }: {
  visible: boolean; onToggle: () => void; disabled?: boolean;
}) {
  const { t } = useTranslation();
  return <InputGroup>
    <InputGroup.Input type={visible ? "text" : "password"} autoComplete="new-password" spellCheck={false} />
    <InputGroup.Suffix><Button type="button" variant="ghost" size="sm" isIconOnly isDisabled={disabled}
      aria-label={t(visible ? "settings.channels.hideSecret" : "settings.channels.showSecret")}
      aria-pressed={visible} onPress={onToggle}>
      {visible ? <EyeOff size={16} /> : <Eye size={16} />}
    </Button></InputGroup.Suffix>
  </InputGroup>;
}
