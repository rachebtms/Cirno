import { Modal } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MemoryCloudScene, type MemoryCloudProps } from "./MemoryCloudScene";

export function MemoryCloud(props: MemoryCloudProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const expandRef = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  useEffect(() => {
    if (!expanded && restoreFocus.current) {
      expandRef.current?.focus({ preventScroll: true });
      restoreFocus.current = false;
    }
  }, [expanded]);
  return <>
    {expanded ? <div className="memory-cloud" aria-hidden="true" /> :
      <MemoryCloudScene {...props} expandRef={expandRef} onExpand={() => setExpanded(true)} />}
    {expanded && <Modal.Backdrop isOpen onOpenChange={open => {
      restoreFocus.current = !open;
      setExpanded(open);
    }}>
      <Modal.Container className="memory-cloud-modal-container" placement="center">
        <Modal.Dialog className="memory-cloud-modal">
          <Modal.Header>
            <Modal.Heading>{t("memoryGraph.cloud")}</Modal.Heading>
            <Modal.CloseTrigger />
          </Modal.Header>
          <MemoryCloudScene {...props} />
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>}
  </>;
}
