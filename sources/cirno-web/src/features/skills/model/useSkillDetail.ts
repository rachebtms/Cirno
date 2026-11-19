import { useCallback, useEffect, useMemo, useState } from "react";
import type { SkillDetail, SkillSummary } from "@/lib/contracts/skills";
import { notifySkillsChanged } from "@/lib/skill-events";
import { useRequest } from "@/ui/resources/useRequest";
import { useMutation } from "@/ui/resources/useMutation";
import { useLifetime } from "@/ui/resources/useLifetime";
import type { SkillService } from "./service";
export function useSkillDetail(service: SkillService, skill: SkillSummary, onClose: () => void) {
  const owner = useMemo(
    () => ({ service, name: skill.name, source: skill.source, decision: null as object | null, busy: false }),
    [service, skill.name, skill.source],
  );
  const read = useRequest<SkillDetail>(owner),
    mutation = useMutation(owner);
  const isCurrent = useLifetime(owner);
  const { load, assign } = read;
  const [deletion, setDeletion] = useState<{ owner: typeof owner; decision: object } | null>(null);
  const decision = deletion?.owner === owner ? deletion.decision : null;
  const deleting = decision !== null && owner.decision === decision;
  const refresh = useCallback(() => load(() => service.read(skill.name)), [load, service, skill.name]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const run = async <T>(request: () => Promise<T>, onSuccess: (value: T) => void) => {
    if (!isCurrent() || owner.busy) return;
    owner.busy = true;
    try { return await mutation.run(request, onSuccess); }
    finally { owner.busy = false; }
  };
  const toggle = () => {
    const detail = read.value;
    if (!detail) return;
    return run(
      () => service.update(skill.name, detail.enabled === false),
      (payload) => {
        notifySkillsChanged(payload);
        if (!isCurrent()) return;
        const updated = payload.skills.find((item) => item.name === skill.name);
        if (updated) assign({ ...detail, ...updated });
        else onClose();
      },
    );
  };
  const remove = () => {
    if (!deleting || owner.decision !== decision) return;
    return run(
      () => service.remove(skill.name),
      (payload) => {
        notifySkillsChanged(payload);
        if (!isCurrent() || owner.decision !== decision) return;
        owner.decision = null;
        setDeletion(null);
        onClose();
      },
    );
  };
  return {
    read,
    mutation,
    refresh,
    toggle,
    remove,
    deleting,
    requestDelete: () => {
      if (!isCurrent() || owner.busy) return;
      mutation.clear();
      owner.decision = {};
      setDeletion({ owner, decision: owner.decision });
    },
    cancelDelete: () => {
      if (!isCurrent() || owner.busy || owner.decision !== decision) return;
      mutation.clear();
      owner.decision = null;
      setDeletion(null);
    },
  };
}
