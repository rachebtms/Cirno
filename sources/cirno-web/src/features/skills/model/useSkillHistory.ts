import { useState } from "react";
import type { WebUIMutationTransport } from "@/lib/api";
import { useMutation } from "@/ui/resources/useMutation";
interface Validation {
  valid: boolean;
  errors: string[];
}
interface SkillHistory {
  validation: Validation;
  versions: { revision: string; path: string; validation: Validation }[];
}
export function useSkillHistory(client: WebUIMutationTransport) {
  const [draft, setDraft] = useState({ client, name: "" });
  const [snapshot, setSnapshot] = useState<{
    client: WebUIMutationTransport;
    name: string;
    result: SkillHistory;
  } | null>(null);
  const mutation = useMutation(client),
    name = draft.client === client ? draft.name : "";
  return {
    name,
    busy: mutation.busy,
    error: mutation.error,
    result: snapshot?.client === client && snapshot.name === name ? snapshot.result : null,
    changeName: (name: string) => {
      setDraft({ client, name });
      setSnapshot(null);
      mutation.clear();
    },
    validate: () =>
      mutation.run(
        () =>
          client.requestMutation<SkillHistory>("instance.action", {
            action: "skills.validate",
            values: { name },
          }),
        (result) => setSnapshot({ client, name, result }),
      ),
  };
}
