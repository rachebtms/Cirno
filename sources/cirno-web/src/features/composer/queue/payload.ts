import type { AttachedImage } from "@/hooks/useAttachedImages";
import type { SendAttachment } from "@/hooks/useCirnoStream";
import type { QueuedPrompt, QueuedPromptImage } from "../contracts";
export function readyImagesToQueuedImages(
  images: AttachedImage[],
): QueuedPromptImage[] {
  return images.map((img) => ({
    dataUrl: img.dataUrl,
    local: img.local,
    kind: img.kind,
    name: img.file.name,
  }));
}

export function queuedImagesToSendImages(
  images?: QueuedPromptImage[],
): SendAttachment[] | undefined {
  if (!images?.length) return undefined;
  return images.flatMap((img): SendAttachment[] => {
    if (img.local)
      return [
        {
          media: { path: img.local.path, name: img.local.name },
          preview: {
            kind: img.local.kind,
            url: img.local.url,
            name: img.local.name,
          },
        },
      ];
    if (!img.dataUrl) return [];
    return [
      {
        media: {
          data_url: img.dataUrl,
          ...(img.name ? { name: img.name } : {}),
        },
        preview: {
          kind:
            img.kind ??
            (img.dataUrl.startsWith("data:image/")
              ? "image"
              : img.dataUrl.startsWith("data:video/")
                ? "video"
                : "file"),
          url: img.dataUrl,
          ...(img.name ? { name: img.name } : {}),
        },
      },
    ];
  });
}

export function queuedAttachmentLabel(prompt: QueuedPrompt, fallback: string): string {
  return prompt.images?.map(image => image.name || image.local?.name || fallback).join(", ") ?? "";
}
export function queuedPromptLabel(prompt: QueuedPrompt, fallback: string): string {
  return prompt.text.trim() || queuedAttachmentLabel(prompt, fallback);
}
