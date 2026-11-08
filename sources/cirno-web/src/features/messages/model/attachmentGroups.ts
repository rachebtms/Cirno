import type { UIImage, UIMediaAttachment } from "@/lib/contracts/messages";
import { toMediaAttachment } from "@/lib/media";

/** Legacy image arrays and typed media describe the same attachment set. */
export function attachmentGroups(
  media: UIMediaAttachment[],
  images: UIImage[],
  inline: ReadonlyMap<string, number>,
) {
  const result = {
    images: [] as UIImage[],
    videos: [] as UIMediaAttachment[],
    files: [] as UIMediaAttachment[],
  };
  const seen = new Set<string>();
  for (const entry of [
    ...images.map((image) => ({ ...image, kind: "image" as const })),
    ...media,
  ]) {
    const item = toMediaAttachment(entry);
    if (item.url) {
      if (seen.has(item.url) || (item.kind === "image" && inline.has(item.url)))
        continue;
      seen.add(item.url);
    }
    if (item.kind === "image") result.images.push(item);
    else if (item.kind === "video") result.videos.push(item);
    else result.files.push(item);
  }
  return result;
}
