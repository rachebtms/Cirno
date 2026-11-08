import { useEffect } from "react";
import { Spinner, Toast, toast } from "@heroui/react";
import { useTranslation } from "react-i18next";
export function OperationNotices({ initialErrors }: { initialErrors?: readonly string[] }) {
    useEffect(() => { for (const error of initialErrors ?? []) toast.danger(error, { timeout: 0 }); }, [initialErrors]);
    const { t } = useTranslation();
    return <Toast.Provider>{({ toast }) => {
            const { title, description, variant, actionProps, indicator, isLoading } = toast.content;
            return <Toast toast={toast} variant={variant}>
      {indicator !== null && <Toast.Indicator variant={variant}>
        {isLoading ? <Spinner size="sm" color="current"/> : indicator}
      </Toast.Indicator>}
      <Toast.Content>
        {title && <Toast.Title>{title}</Toast.Title>}
        {description && <Toast.Description>{description}</Toast.Description>}
      </Toast.Content>
      {actionProps?.children && <Toast.ActionButton {...actionProps}/>}
      <Toast.CloseButton aria-label={t("common.close")}/>
    </Toast>;
        }}</Toast.Provider>;
}
