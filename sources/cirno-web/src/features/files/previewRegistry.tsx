import type { FilePreviewPayload } from "@/lib/contracts/files";
import type { ComponentType } from "react";
import { useState } from "react";
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
  const [failed, setFailed] = useState(false);
  if (file.kind !== "video")
    throw new Error("Video renderer received a non-video file");
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-3 p-4">
      <video
        controls
        playsInline
        preload="metadata"
        src={file.url}
        className="max-h-full max-w-full"
        aria-label={file.display_path}
        onError={() => setFailed(true)}
      />
      {failed && (
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
