/** Files operations for the versioned Cirno API. */

import type {
  FilePreviewPayload,
  FileReferenceMetadata,
} from "@/lib/contracts/files";
import { API_READ_TIMEOUT_MS, request } from "./transport";

export async function fetchFilePreview(
  token: string,
  key: string,
  path: string,
  base: string = "",
): Promise<FilePreviewPayload> {
  const query = new URLSearchParams();
  query.set("path", path);
  return request<FilePreviewPayload>(
    `${base}/v0/sessions/${encodeURIComponent(key)}/file-preview?${query}`,
    token,
    { cache: "no-store" },
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchFileReferenceMetadata(
  token: string,
  key: string,
  path: string,
): Promise<FileReferenceMetadata> {
  const query = new URLSearchParams({ path, metadata: "1" });
  return request<FileReferenceMetadata>(
    `/v0/sessions/${encodeURIComponent(key)}/file-preview?${query}`,
    token,
    { cache: "no-store" },
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchFilePreviewAvailability(
  token: string,
  key: string,
  path: string,
  base: string = "",
): Promise<boolean> {
  const query = new URLSearchParams();
  query.set("path", path);
  query.set("probe", "1");
  const payload = await request<{ available?: boolean }>(
    `${base}/v0/sessions/${encodeURIComponent(key)}/file-preview?${query}`,
    token,
    { cache: "no-store" },
    API_READ_TIMEOUT_MS,
  );
  return payload.available !== false;
}
