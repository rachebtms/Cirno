import { useMemo, useState } from "react";
import type { MarketplaceSkillSummary } from "@/lib/contracts/skills";
import { notifySkillsChanged } from "@/lib/skill-events";
import { useMutation } from "@/ui/resources/useMutation";
import { useLifetime } from "@/ui/resources/useLifetime";
import type { SkillService } from "./service";
export function useMarketplaceInstall(service: SkillService) {
  const owner = useMemo(() => ({
    service, choice: null as { skill: MarketplaceSkillSummary } | null, installing: false,
  }), [service]);
  const isCurrent = useLifetime(owner);
  const operation = useMutation(owner);
  const [selection, setSelection] = useState<{
    owner: typeof owner;
    choice: NonNullable<typeof owner.choice>;
  } | null>(null);
  const choice = selection?.owner === owner ? selection.choice : null;
  const selected = choice?.skill ?? null;
  return {
    operation,
    selected,
    select: (skill: MarketplaceSkillSummary) => {
      if (!isCurrent() || owner.installing) return;
      operation.clear();
      owner.choice = { skill };
      setSelection({ owner, choice: owner.choice });
    },
    close: () => {
      if (isCurrent() && !owner.installing && owner.choice === choice) {
        operation.clear();
        owner.choice = null;
        setSelection(null);
      }
    },
    install: async () => {
      if (!isCurrent() || !choice || owner.choice !== choice || owner.installing) return;
      owner.installing = true;
      try {
        return await operation.run(
          () => service.install(choice.skill),
          (payload) => {
            notifySkillsChanged(payload);
            if (!isCurrent() || owner.choice !== choice) return;
            owner.choice = null;
            setSelection(null);
          },
        );
      } finally {
        owner.installing = false;
      }
    },
  };
}
