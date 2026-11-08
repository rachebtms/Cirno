import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it } from "vitest";
import { ProviderIcon } from "@/features/settings/shared/ProviderIcon";
import { __clearLogoFallbackCacheForTests } from "@/hooks/useLogoFallback";
import { providerBrand } from "@/lib/provider-brand";

beforeEach(__clearLogoFallbackCacheForTests);
afterEach(cleanup);
it("uses alternate image sources before falling back to readable initials", () => {
  const view = render(<ProviderIcon provider="moonshot" showBrandLogos />);
  for (const url of providerBrand("moonshot")!.logoUrls) {
    const image = view.container.querySelector("img")!;
    expect(image).toHaveAttribute("src", url);
    fireEvent.error(image);
  }
  expect(view.container.querySelector("img")).toBeNull();
  expect(view.container).toHaveTextContent("MS");
});
it("does not request a remote image when brand logos are disabled", () => {
  const view = render(<ProviderIcon provider="moonshot" showBrandLogos={false} />);
  expect(view.container.querySelector("img")).toBeNull();
  expect(view.container.querySelector("svg")).not.toBeNull();
});
