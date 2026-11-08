import { Button } from "@heroui/react";
import { ChevronUp, Target } from "lucide-react";
import { DetailsPopover } from "@/ui/overlays/DetailsPopover";
import { MarkdownText } from "@/components/MarkdownText";
import { buildGoalMarkdownBody, goalStateStripPreview } from "../goal-presentation";
import { useComposerView } from "./context";

export function ComposerGoal() {
  const { inputs, composerState: state } = useComposerView();
  const label = goalStateStripPreview(inputs.goalState, state.t);
  if (!label) return null;
  const body = buildGoalMarkdownBody(inputs.goalState?.ui_summary ?? "", inputs.goalState?.objective ?? "");
  return <div className="composer-goal" role="status" aria-label={state.t("thread.composer.goalStateStrip", { label })}>
    <Target size={16} aria-hidden /><span>{label}</span>
    {body && <DetailsPopover title={state.t("thread.composer.goalStateSheetTitle")} className="composer-goal-popover" trigger={
      <Button type="button" isIconOnly size="sm" variant="ghost" aria-label={state.t("thread.composer.goalStateExpandAria")}><ChevronUp size={16} /></Button>
    }><MarkdownText>{body}</MarkdownText></DetailsPopover>}

  </div>;
}
