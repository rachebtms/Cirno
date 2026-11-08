import { useRef, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";

export function SplitDivider({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const { t } = useTranslation();
  const bounds = useRef<DOMRect | null>(null);
  const update = (value: number) => onChange(Math.max(25, Math.min(75, value)));
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId) || !bounds.current) return;
    update((event.clientX - bounds.current.left) / bounds.current.width * 100);
  };
  return <div role="separator" aria-orientation="vertical" aria-valuenow={Math.round(value)} aria-valuemin={25} aria-valuemax={75}
    aria-label={t("workspace.resizeSplit")} tabIndex={0} className="workbench-split-divider"
    onPointerDown={event => {
      bounds.current = event.currentTarget.parentElement!.getBoundingClientRect();
      event.currentTarget.setPointerCapture(event.pointerId);
      event.preventDefault();
    }} onPointerMove={move} onPointerUp={event => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    }} onKeyDown={event => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault(); update(value + (event.key === "ArrowLeft" ? -2 : 2));
      }
      if (event.key === "Home") { event.preventDefault(); update(25); }
      if (event.key === "End") { event.preventDefault(); update(75); }
    }} />;
}
