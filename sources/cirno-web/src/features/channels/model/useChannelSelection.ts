import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation } from "@/ui/resources/useMutation";
type Completion = () => Promise<boolean>;
export function useChannelSelection(
  owner: unknown,
  register?: (handler: Completion | null) => void,
) {
  const [selection, setSelection] = useState<{
    owner: unknown;
    name: string;
    connect: number;
  } | null>(null);
  const beforeClose = useRef<Completion | null>(null),
    mutation = useMutation(owner);
  const setCompletion = useCallback(
    (handler: Completion | null) => {
      beforeClose.current = handler;
      register?.(handler);
    },
    [register],
  );
  useEffect(
    () => () => {
      beforeClose.current = null;
      register?.(null);
    },
    [owner, register],
  );
  const { run, clear } = mutation;
  return {
    selected: selection?.owner === owner ? selection : null,
    mutation,
    setCompletion,
    select: (name: string, connect = false) => {
      clear();
      setCompletion(null);
      setSelection({ owner, name, connect: connect ? 1 : 0 });
    },
    close: () =>
      run(
        async () => (await beforeClose.current?.()) ?? true,
        (canClose) => {
          if (canClose) {
            setCompletion(null);
            setSelection(null);
          }
        },
      ),
  };
}
