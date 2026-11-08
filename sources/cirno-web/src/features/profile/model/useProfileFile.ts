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
  const { load, assign } = resource;
  const refresh = useCallback(() => load(service.read), [load, service]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  // Content and revision belong to the same editor opening, independently of reloads.
  const edit = useRef<{ service: typeof service; file: ProfileFile } | null>(null);
  const opening = useRef(0);
  useEffect(
    () => () => {
      opening.current += 1;
    },
    [service],
  );
  const loadForEdit = async () => {
    const generation = ++opening.current;
    const file = await service.read();
    if (generation === opening.current) edit.current = { service, file };
    return file.content;
  };
  const save = async (content: string) => {
    const snapshot = edit.current!;
    const saved = await snapshot.service.save(content, snapshot.file.revision);
    assign(saved);
  };
  return { ...resource, refresh, loadForEdit, save };
}
