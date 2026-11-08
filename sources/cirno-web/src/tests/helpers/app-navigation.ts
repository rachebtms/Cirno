import i18n from "@/i18n";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

export async function openAppCatalog() {
  fireEvent.click(
    await screen.findByRole("button", {
      name: i18n.t("workspace.openItem", {
        title: i18n.t("workspace.library"),
      }),
    }),
  );
  const heading = await screen.findByRole("heading", {
    name: i18n.t("workspace.library"),
  });
  return heading.closest<HTMLElement>("section")!;
}

export async function openAppConversation(title: string) {
  const tab = screen.queryByRole("tab", { name: title });
  if (tab) fireEvent.click(tab);
  else
    fireEvent.click(
      await within(await openAppCatalog()).findByRole("button", {
        name: title,
      }),
    );
}

export async function closeAppConversationTab(title: string) {
  fireEvent.click(
    await screen.findByRole("button", {
      name: i18n.t("workspace.closeTab", { title }),
    }),
  );
}

export async function startAppTemporaryConversation(content: string) {
  fireEvent.click(
    await screen.findByRole("button", { name: "Temporary chat" }),
  );
  fireEvent.change(
    await screen.findByRole("textbox", { name: "Message input" }),
    { target: { value: content } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => {
    if (!window.location.hash.startsWith("#/temporary/"))
      throw new Error("Temporary conversation has not been admitted");
  });
  return window.location.hash;
}

/** Retained inactive chat tabs remain mounted; assertions target the visible surface. */
export function visibleThreadRegion() {
  const regions = screen.queryAllByTestId("thread-message-region").filter(region => !region.closest("[hidden], [aria-hidden='true']"));
  if (regions.length !== 1) throw new Error(`Expected one visible chat region, found ${regions.length}`);
  return regions[0];
}
