import "./model-selection.css";
import { Layers } from "lucide-react";
import { useLogoFallback } from "@/hooks/useLogoFallback";
import { inferProviderFromModelName, providerBrand } from "@/lib/provider-brand";

export function PresetProviderIcon({ label, modelDetail, provider, testId }: {
  label: string;
  modelDetail?: string | null;
  provider?: string | null;
  testId?: string;
}) {
  const brand = providerBrand(provider || inferProviderFromModelName(modelDetail || label));
  const { logoUrl, logoLoaded, onLogoError, onLogoLoad } = useLogoFallback(brand?.logoUrls);
  const tile = brand?.logoLayout === "tile" && logoUrl === brand.logoUrl;
  return <span data-testid={testId} className="model-provider-icon" aria-hidden style={{ backgroundColor: logoLoaded && !tile ? "white" : undefined }}>
    <span className="model-provider-fallback" style={{ backgroundColor: brand?.color, color: brand ? "white" : undefined, opacity: logoLoaded ? 0 : 1 }}>
      {brand ? brand.initials.slice(0, 2) : <Layers size={14} />}
    </span>
    {logoUrl && <img src={logoUrl} alt="" draggable={false} loading="lazy" referrerPolicy="no-referrer"
      style={{ opacity: logoLoaded ? 1 : 0, padding: tile ? 0 : 2 }} onLoad={onLogoLoad} onError={onLogoError} />}
  </span>;
}
