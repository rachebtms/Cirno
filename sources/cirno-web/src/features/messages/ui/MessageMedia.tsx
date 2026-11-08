import { ImageGallery } from "@/components/ImageGallery";
import { AttachmentTile } from "@/components/AttachmentTile";
import { useInlineImages } from "@/components/InlineImageContext";
import type { UIImage, UIMediaAttachment } from "@/lib/contracts/messages";
import { attachmentGroups } from "../model/attachmentGroups";

export function MessageMedia({
  media = [],
  images = [],
  align,
  pending = false,
}: {
  media?: UIMediaAttachment[];
  images?: UIImage[];
  align: "left" | "right";
  pending?: boolean;
}) {
  const groups = attachmentGroups(media, images, useInlineImages());
  if (!groups.images.length && !groups.videos.length && !groups.files.length)
    return null;
  return (
    <div className={`message-media message-media-${align}`}>
      {groups.images.length > 0 && (
        <ImageGallery
          images={groups.images}
          align={align}
          size={align === "left" ? "large" : "compact"}
        />
      )}
      {groups.videos.map((item, i) => (
        <AttachmentTile
          key={`video-${item.url ?? i}`}
          attachment={item}
          pending={pending}
          className="my-0"
        />
      ))}
      {groups.files.length > 0 && (
        <div className="message-media-files">
          {groups.files.map((item, i) => (
            <AttachmentTile
              key={`file-${item.url ?? i}`}
              attachment={item}
              pending={pending}
            />
          ))}
        </div>
      )}
    </div>
  );
}
