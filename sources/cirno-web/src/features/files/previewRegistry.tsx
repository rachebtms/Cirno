import type { FilePreviewPayload } from "@/lib/contracts/files";
import type { ComponentType } from "react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export interface FilePreviewRendererProps {
  file: FilePreviewPayload;
  onOpenFile?: (path: string) => void;
}
export interface FilePreviewRenderer {
  id: string;
  supports: (file: FilePreviewPayload) => boolean;
  Content: ComponentType<FilePreviewRendererProps>;
}

function VideoPreview({ file }: FilePreviewRendererProps) {
  const { t } = useTranslation();
  const [failed, setFailed] = useState<FilePreviewPayload | null>(null);
  const element = useRef<HTMLVideoElement>(null);
  const previous = useRef(file);
  useEffect(() => {
    const prior = previous.current;
    previous.current = file;
    setFailed(null);
    // Borrowed URLs identify a path, so Reload can return a new snapshot with
    // the same URL. A changed src already reloads the media element itself.
    if (prior !== file && prior.kind === "video" && file.kind === "video" && prior.url === file.url)
      element.current?.load();
  }, [file]);
  if (file.kind !== "video")
    throw new Error("Video renderer received a non-video file");
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-3 p-4">
      <video
        ref={element}
        controls
        playsInline
        preload="metadata"
        src={file.url}
        className="max-h-full max-w-full"
        aria-label={file.display_path}
        onError={() => setFailed(file)}
        onLoadedData={() => setFailed(null)}
      />
      {failed === file && (
        <p role="alert" className="text-sm text-destructive">
          {t("filePreview.failed")}
        </p>
      )}
    </div>
  );
}
const mediaRenderer: FilePreviewRenderer = {
  id: "video",
  supports: (file) => file.kind === "video",
  Content: VideoPreview,
};

/** Optional format renderers run before the shared image/text/Markdown view. */
export function createFilePreviewRegistry(
  contributions: readonly FilePreviewRenderer[] = [],
) {
  const renderers = [...contributions, mediaRenderer];
  if (new Set(renderers.map((item) => item.id)).size !== renderers.length)
    throw new Error("File preview renderer IDs must be unique");
  return Object.freeze({
    find: (file: FilePreviewPayload) =>
      renderers.find((item) => item.supports(file)),
  });
}
export const filePreviewRenderers = createFilePreviewRegistry();
