import { useState } from "react";
import type { MarketplaceSkillSummary } from "@/lib/contracts/skills";
import { notifySkillsChanged } from "@/lib/skill-events";
import { useMutation } from "@/ui/resources/useMutation";
import type { SkillService } from "./service";
export function useMarketplaceInstall(service: SkillService) {
  const operation = useMutation(service);
  const [selection, setSelection] = useState<{
    service: SkillService;
    skill: MarketplaceSkillSummary;
  } | null>(null);
  const selected = selection?.service === service ? selection.skill : null;
  return {
    operation,
    selected,
    select: (skill: MarketplaceSkillSummary) => {
      operation.clear();
      setSelection({ service, skill });
    },
    close: () => {
      if (!operation.busy) {
        operation.clear();
        setSelection(null);
      }
    },
    install: () =>
      selected &&
      operation.run(
        () => service.install(selected),
        (payload) => {
          notifySkillsChanged(payload);
          setSelection(null);
        },
      ),
  };
}
