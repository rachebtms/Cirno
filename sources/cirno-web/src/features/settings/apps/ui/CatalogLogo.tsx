import { useMemo } from "react";
import { useLogoFallback } from "@/hooks/useLogoFallback";
import { isGenericRepositoryLogoUrl, logoFallbackUrls } from "@/lib/provider-brand";

export function CatalogLogo({ name, logo, color, show, cli = false }: { name: string; logo?: string | null; color?: string | null; show: boolean; cli?: boolean }) {
  const urls = useMemo(() => cli && isGenericRepositoryLogoUrl(logo) ? [] : logoFallbackUrls(logo), [logo, cli]);
  const image = useLogoFallback(urls);
  const showImage = show && Boolean(image.logoUrl);
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]?.toUpperCase()).join("");
  return <span className="catalog-logo" style={{ color: color || undefined }}>
    {(!showImage || !image.logoLoaded) && <span aria-hidden>{initials}</span>}
    {showImage && <img src={image.logoUrl!} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" draggable={false}
      onLoad={image.onLogoLoad} onError={image.onLogoError} data-loaded={image.logoLoaded || undefined} />}
  </span>;
}
