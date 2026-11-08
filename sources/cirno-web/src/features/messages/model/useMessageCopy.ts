import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { copyTextToClipboard } from "@/lib/clipboard";
import { useMutation } from "@/ui/resources/useMutation";

export function useMessageCopy(text: string) {
  const { t } = useTranslation(),
    owner = useMemo(() => ({ length: text.length }), [text]);
  const mutation = useMutation(owner),
    timer = useRef<number | undefined>(undefined);
  const [copiedOwner, setCopiedOwner] = useState<object | null>(null);
  useEffect(() => () => window.clearTimeout(timer.current), [owner]);
  return {
    copied: copiedOwner === owner,
    label: t(
      copiedOwner === owner ? "message.copiedReply" : "message.copyReply",
    ),
    error: mutation.error,
    busy: mutation.busy,
    copy: () =>
      mutation.run(
        async () => {
          if (!(await copyTextToClipboard(text)))
            throw new Error(t("common.copyFailed"));
        },
        () => {
          setCopiedOwner(owner);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => setCopiedOwner(null), 1500);
        },
      ),
  };
}
