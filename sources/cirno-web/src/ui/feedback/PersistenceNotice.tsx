import { Alert, Button } from "@heroui/react";
import { useTranslation } from "react-i18next";

export function PersistenceNotice({ title, detail, retry, disabled, className }: {
  title: string; detail: string; retry: () => void; disabled?: boolean; className?: string;
}) {
  const { t } = useTranslation();
  return <Alert status="danger" role="alert" className={className}><Alert.Content>
    <Alert.Title>{title}</Alert.Title><Alert.Description>{detail}</Alert.Description>
    <Button type="button" size="sm" variant="secondary" isDisabled={disabled} onPress={retry}>{t("common.retry")}</Button>
  </Alert.Content></Alert>;
}
