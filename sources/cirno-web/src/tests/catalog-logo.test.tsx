import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { CatalogLogo } from "@/features/settings/apps/ui/CatalogLogo";
import { __clearLogoFallbackCacheForTests } from "@/hooks/useLogoFallback";

beforeEach(__clearLogoFallbackCacheForTests);

it("keeps the app identifiable when its remote logo fails", () => {
  const { container } = render(<CatalogLogo name="Research Tools" logo="/failed-logo.svg" show />);
  const image = container.querySelector("img")!;
  expect(image).toHaveAttribute("src", "/failed-logo.svg");
  fireEvent.error(image);
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("RT")).toBeVisible();
});

it("does not request a remote logo when brand logos are disabled", () => {
  const { container } = render(<CatalogLogo name="Research Tools" logo="/unused-logo.svg" show={false} />);
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("RT")).toBeVisible();
});
