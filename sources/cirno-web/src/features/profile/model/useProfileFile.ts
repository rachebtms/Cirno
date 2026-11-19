import { useCallback, useEffect, useMemo, useRef } from "react";
import type { WebUIMutationTransport } from "@/lib/api";
import { useRequest } from "@/ui/resources/useRequest";

export interface ProfileFile {
  name: string;
  file: string;
  content: string;
  revision: string;
}
export function useProfileFile(client: WebUIMutationTransport, name: string) {
  const service = useMemo(
    () => ({
      read: () => client.requestMutation<ProfileFile>("settings.profile.read", { name }),
      save: (content: string, revision: string) =>
        client.requestMutation<ProfileFile>("settings.profile.update", { name, content, revision }),
    }),
    [client, name],
  );
  const resource = useRequest<ProfileFile>(service);
  const { load, assign, isCurrent } = resource;
  const refresh = useCallback(() => load(service.read), [load, service]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  // Content and revision belong to the same editor opening, independently of reloads.
  const edit = useRef<{ lifetime: typeof isCurrent; file: ProfileFile; saving: boolean } | null>(null);
  const opening = useRef(0);
  useEffect(
    () => () => {
      opening.current += 1;
    },
    [isCurrent],
  );
  const requireCurrent = useCallback(() => {
    if (!isCurrent()) throw new Error("This editor is no longer active; reopen the file before editing");
  }, [isCurrent]);
  const loadForEdit = useCallback(async () => {
    requireCurrent();
    const generation = ++opening.current;
    edit.current = null;
    const file = await service.read();
    requireCurrent();
    if (generation !== opening.current) throw new Error("This editor opening was superseded; reopen the file");
    edit.current = { lifetime: isCurrent, file, saving: false };
    return file.content;
  }, [requireCurrent, service, isCurrent]);
  const save = useCallback(async (content: string) => {
    requireCurrent();
    const snapshot = edit.current;
    if (!snapshot || snapshot.lifetime !== isCurrent)
      throw new Error("Reload the file before saving so its current revision can be checked");
    if (snapshot.saving) throw new Error("This file is already being saved");
    snapshot.saving = true;
    try {
      const saved = await service.save(content, snapshot.file.revision);
      if (isCurrent() && edit.current === snapshot) {
        snapshot.file = saved;
        assign(saved);
      }
    } finally {
      snapshot.saving = false;
    }
  }, [requireCurrent, isCurrent, service, assign]);
  return { ...resource, refresh, loadForEdit, save };
}
