import { Button, Popover } from "@heroui/react";
import { X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import "./details-popover.css";

export function DetailsPopover({ trigger, title, children, className = "" }: {
  trigger: ReactNode;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return <Popover isOpen={open} onOpenChange={setOpen}>
    {trigger}
    <Popover.Content placement="top" className={`details-popover ${className}`}>
      <Popover.Dialog aria-label={title}>
        <header><h2>{title}</h2><Button type="button" isIconOnly size="sm" variant="ghost" aria-label={t("common.close")} onPress={() => setOpen(false)}><X size={16} /></Button></header>
        {children}
      </Popover.Dialog>
    </Popover.Content>
  </Popover>;
}
