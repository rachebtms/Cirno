import { useCallback, useEffect, useMemo, useState } from "react";
import type { SkillDetail, SkillSummary } from "@/lib/contracts/skills";
import { notifySkillsChanged } from "@/lib/skill-events";
import { useRequest } from "@/ui/resources/useRequest";
import { useMutation } from "@/ui/resources/useMutation";
import type { SkillService } from "./service";
export function useSkillDetail(service: SkillService, skill: SkillSummary, onClose: () => void) {
  const owner = useMemo(
    () => ({ service, name: skill.name, source: skill.source }),
    [service, skill.name, skill.source],
  );
  const read = useRequest<SkillDetail>(owner),
    mutation = useMutation(owner);
  const { load, assign } = read;
  const [deleting, setDeleting] = useState(false);
  const refresh = useCallback(() => load(() => service.read(skill.name)), [load, service, skill.name]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const toggle = () =>
    mutation.run(
      () => service.update(skill.name, read.value!.enabled === false),
      (payload) => {
        notifySkillsChanged(payload);
        const updated = payload.skills.find((item) => item.name === skill.name);
        if (updated) assign({ ...read.value!, ...updated });
        else onClose();
      },
    );
  const remove = () =>
    mutation.run(
      () => service.remove(skill.name),
      (payload) => {
        notifySkillsChanged(payload);
        onClose();
      },
    );
  return {
    read,
    mutation,
    refresh,
    toggle,
    remove,
    deleting,
    requestDelete: () => {
      mutation.clear();
      setDeleting(true);
    },
    cancelDelete: () => {
      mutation.clear();
      setDeleting(false);
    },
  };
}
