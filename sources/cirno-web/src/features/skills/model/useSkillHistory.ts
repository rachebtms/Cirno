import { useMemo, useState } from "react";
import type { WebUIMutationTransport } from "@/lib/api";
import { useMutation } from "@/ui/resources/useMutation";
import { useLifetime } from "@/ui/resources/useLifetime";
interface Validation {
  valid: boolean;
  errors: string[];
}
interface SkillHistory {
  validation: Validation;
  versions: { revision: string; path: string; validation: Validation }[];
}
export function useSkillHistory(client: WebUIMutationTransport) {
  const owner = useMemo(() => ({ client, draft: { name: "" } }), [client]);
  const isCurrent = useLifetime(owner);
  const [selection, setSelection] = useState({ owner, draft: owner.draft });
  const draft = selection.owner === owner ? selection.draft : owner.draft;
  const [snapshot, setSnapshot] = useState<{
    owner: typeof owner;
    draft: typeof draft;
    result: SkillHistory;
  } | null>(null);
  const mutation = useMutation(owner),
    name = draft.name;
  return {
    name,
    busy: mutation.busy,
    error: mutation.error,
    result: snapshot?.owner === owner && snapshot.draft === draft ? snapshot.result : null,
    changeName: (name: string) => {
      if (!isCurrent()) return;
      owner.draft = { name };
      setSelection({ owner, draft: owner.draft });
      setSnapshot(null);
      mutation.clear();
    },
    validate: () => {
      if (!isCurrent() || owner.draft !== draft) return;
      return mutation.run(
        () =>
          client.requestMutation<SkillHistory>("instance.action", {
            action: "skills.validate",
            values: { name },
          }),
        (result) => {
          if (isCurrent() && owner.draft === draft) setSnapshot({ owner, draft, result });
        },
      );
    },
  };
}
