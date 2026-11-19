import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { filePreviewRenderers } from "@/features/files/previewRegistry";
import type { FilePreviewPayload } from "@/lib/contracts/files";
import { setAppLanguage } from "@/i18n";

const video: FilePreviewPayload = { kind: "video", path: "/project/clip.mp4", display_path: "clip.mp4", project_path: "/project",
  size: 4, mime_type: "video/mp4", url: "/v0/media/signed/clip" };
const Content = filePreviewRenderers.find(video)!.Content;
beforeEach(async () => { await setAppLanguage("en"); vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {}); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("does not carry a failed video's error into another signed URL", async () => {
  const ui = render(<Content file={video} />);
  fireEvent.error(screen.getByLabelText("clip.mp4"));
  await screen.findByRole("alert");
  ui.rerender(<Content file={{ ...video, url: "/v0/media/renewed/clip" }} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(HTMLMediaElement.prototype.load).not.toHaveBeenCalled();
});

it("retries the media element after reloading a borrowed file with the same URL", async () => {
  const ui = render(<Content file={video} />);
  fireEvent.error(screen.getByLabelText("clip.mp4"));
  await screen.findByRole("alert");
  ui.rerender(<Content file={{ ...video }} />);
  await waitFor(() => expect(HTMLMediaElement.prototype.load).toHaveBeenCalledOnce());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("clears a media error when the current file starts loading successfully", async () => {
  render(<Content file={video} />);
  const element = screen.getByLabelText("clip.mp4");
  fireEvent.error(element);
  await screen.findByRole("alert");
  fireEvent.loadedData(element);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
