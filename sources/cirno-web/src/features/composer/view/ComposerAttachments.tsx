import { Button, Spinner } from "@heroui/react";
import { File, X } from "lucide-react";
import { DetailsPopover } from "@/ui/overlays/DetailsPopover";
import { useId } from "react";
import type { AttachedImage } from "@/hooks/useAttachedImages";
import { formatBytes } from "../contracts";
import { useComposerView } from "./context";

export function ComposerAttachments() {
  const { composerState: state } = useComposerView();
  if (!state.images.length) return null;
  return <div className="composer-attachments" aria-label={state.t("thread.composer.attachImage")}>
    {state.images.map(image => <AttachmentTile key={image.id} image={image} />)}
  </div>;
}

function AttachmentTile({ image }: { image: AttachedImage }) {
      const { composerState: state, composerKeyboard: keyboard } = useComposerView();
      const nameId = useId();
      const error = image.status === "error" && image.error ? image.error === "too_large"
        ? state.formatUploadTooLarge(image.file.size, image.kind === "video" ? state.maxVideoBytes : state.maxFileBytes)
        : state.formatRejection(image.error) : null;
      const size = image.status === "ready" && image.normalized && image.encodedBytes
        ? state.t("thread.composer.normalizedSizeHint", { orig: formatBytes(image.file.size), current: formatBytes(image.encodedBytes) }) : formatBytes(image.file.size);
      const details = <div className="composer-attachment-details"><span>{size}</span></div>;
      const format = image.file.name.match(/\.(tar\.(?:gz|bz2|xz)|[a-z0-9]{1,12})$/i)?.[1].toUpperCase();
      return <div className="composer-attachment" data-invalid={Boolean(error) || undefined} data-testid="composer-chip">
        <div className="composer-attachment-preview">
          <DetailsPopover title={image.file.name} trigger={<Button type="button" variant="ghost" className="composer-attachment-open" aria-label={image.file.name} aria-describedby={`${nameId}-size`}>
              {image.kind === "image" && image.status !== "error" && image.previewUrl ? <img src={image.previewUrl} alt={image.file.name} draggable={false} />
                : <span className="composer-attachment-format" aria-hidden><File size={24} /><span>{format}</span></span>}
              {image.status === "encoding" && <Spinner size="sm" aria-label={state.t("thread.composer.encoding")} />}
            </Button>}>{details}</DetailsPopover>
          <Button type="button" isIconOnly variant="secondary" size="sm" aria-label={state.t("thread.composer.remove")}
            aria-describedby={nameId} onPress={() => keyboard.removeChip(image.id)} onKeyDown={keyboard.onChipKey(image.id)}
            ref={element => { if (element) state.chipRefs.current.set(image.id, element); else state.chipRefs.current.delete(image.id); }}>
            <X size={14} aria-hidden />
          </Button>
        </div>
        <span id={nameId} className="composer-attachment-name" title={image.file.name}>{image.file.name}</span><span id={`${nameId}-size`}>{size}</span>
        {error && <p role="alert">{error}</p>}
      </div>;
}
