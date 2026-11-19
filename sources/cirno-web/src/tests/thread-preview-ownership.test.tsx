import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useThreadPreview } from "@/components/thread/useThreadPreview";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import type { FilePreviewPayload, FileReferenceMetadata } from "@/lib/contracts/files";
import { fetchFilePreview, fetchFilePreviewAvailability, fetchFileReferenceMetadata } from "@/lib/api";

vi.mock("@/lib/api", async () => ({
  ApiError: (await import("@/lib/api/transport")).ApiError,
  fetchFilePreview: vi.fn(), fetchFilePreviewAvailability: vi.fn(), fetchFileReferenceMetadata: vi.fn(),
}));

const payload = { kind: "text" as const, path: "/first/notes.txt", display_path: "notes.txt", project_path: "/first",
  content: "First context", language: "text", size: 4, truncated: false };
function client() { return { requestMutation: vi.fn().mockResolvedValue({ available: false }) } as unknown as CirnoClient; }
function scope(project_path = "/first", access_mode = "full") { return { project_path, access_mode } as WorkspaceScopePayload; }
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function setup(temporary = false) {
  let options: Parameters<typeof useThreadPreview>[0] = { chatId: "owner", previewSessionKey: "websocket:owner", workspaceScope: scope(),
    temporary, headerActive: true, messageCount: 1 };
  let source = client(), token = "first-token";
  let model!: ReturnType<typeof useThreadPreview>;
  function Read() { model = useThreadPreview(options); return null; }
  const view = () => <ClientProvider client={source} token={token}><Read /></ClientProvider>;
  const ui = render(view());
  return {
    get model() { return model; },
    change(kind: string) {
      if (kind === "client") source = client();
      if (kind === "token") token = "renewed-token";
      if (kind === "scope") options = { ...options, workspaceScope: scope("/second") };
      if (kind === "access") options = { ...options, workspaceScope: scope("/first", "restricted") };
      if (kind === "temporary") options = { ...options, temporary: !options.temporary };
      if (kind === "session") options = { ...options, chatId: "second", previewSessionKey: "websocket:second" };
      if (kind === "equivalent") options = { ...options, workspaceScope: { ...scope() } };
      ui.rerender(view());
    },
  };
}
beforeEach(() => {
  vi.mocked(fetchFilePreviewAvailability).mockReset().mockResolvedValue(true);
  vi.mocked(fetchFilePreview).mockReset().mockResolvedValue(payload);
  vi.mocked(fetchFileReferenceMetadata).mockReset().mockResolvedValue({ path: payload.path, relative_path: "notes.txt" });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each(["client", "scope", "access", "temporary"])("rechecks positive preview availability after %s changes", async kind => {
  const ui = setup();
  expect(await ui.model.resolveFilePreviewAvailability("notes.txt")).toBe(true);
  vi.mocked(fetchFilePreviewAvailability).mockResolvedValue(false);
  ui.change(kind);
  expect(await ui.model.resolveFilePreviewAvailability("notes.txt")).toBe(false);
});

it.each(["scope", "access"])("does not reuse cached file contents after %s changes", async kind => {
  const ui = setup();
  expect(await ui.model.filePreviews.load("notes.txt")).toMatchObject({ content: "First context" });
  vi.mocked(fetchFilePreview).mockResolvedValue({ ...payload, content: "Second context" });
  ui.change(kind);
  expect(await ui.model.filePreviews.load("notes.txt")).toMatchObject({ content: "Second context" });
  expect(fetchFilePreview).toHaveBeenCalledTimes(2);
});

it("does not retain a transient failed availability request as a negative result", async () => {
  const ui = setup();
  vi.mocked(fetchFilePreviewAvailability).mockRejectedValueOnce(new Error("Transient connection loss"));
  expect(await ui.model.resolveFilePreviewAvailability("notes.txt")).toBe(false);
  expect(await ui.model.resolveFilePreviewAvailability("notes.txt")).toBe(true);
  expect(fetchFilePreviewAvailability).toHaveBeenCalledTimes(2);
});

it.each(["session", "scope"])("retires pending preview actions after %s changes", kind => {
  const ui = setup(), previous = vi.fn(), next = vi.fn();
  act(() => { ui.model.setBrowserDirty(true); });
  act(() => { ui.model.guardPreview(previous); });
  expect(ui.model.pendingPreviewAction).not.toBeNull();
  const previousConfirmation = ui.model.pendingPreviewAction;
  ui.change(kind);
  expect(ui.model.pendingPreviewAction).toBeNull();
  act(() => { ui.model.guardPreview(next); });
  act(() => { previousConfirmation?.(); });
  expect(next).toHaveBeenCalledOnce();
  expect(previous).not.toHaveBeenCalled();
});

it.each(["metadata", "contents"])("refuses a retired context's retained %s loader", async kind => {
  const ui = setup();
  await ui.model.filePreviews.load("notes.txt");
  const previous = kind === "metadata" ? ui.model.fileActions.resolveMetadata : ui.model.filePreviews.load;
  ui.change("scope");
  await expect(previous("notes.txt")).rejects.toThrow(/context|active|changed/i);
  expect(fetchFilePreview).toHaveBeenCalledTimes(1);
  expect(fetchFileReferenceMetadata).not.toHaveBeenCalled();
});

it("keeps hot previews for equivalent scopes and token renewal, using the renewed token on revalidation", async () => {
  const clock = vi.spyOn(Date, "now").mockReturnValue(100);
  const ui = setup();
  await ui.model.filePreviews.load("notes.txt");
  await ui.model.resolveFilePreviewAvailability("notes.txt");
  const original = ui.model.filePreviews;
  ui.change("equivalent");
  ui.change("token");
  expect(ui.model.filePreviews).toBe(original);
  await ui.model.filePreviews.load("notes.txt");
  await ui.model.resolveFilePreviewAvailability("notes.txt");
  expect(fetchFilePreview).toHaveBeenCalledOnce();
  expect(fetchFilePreviewAvailability).toHaveBeenCalledOnce();
  clock.mockReturnValue(6100);
  await ui.model.filePreviews.load("notes.txt");
  expect(fetchFilePreview).toHaveBeenLastCalledWith("renewed-token", "websocket:owner", "notes.txt");
});

it("shares an in-flight availability probe within the same request owner", async () => {
  const result = pending<boolean>(), ui = setup();
  vi.mocked(fetchFilePreviewAvailability).mockReturnValueOnce(result.promise);
  const first = ui.model.resolveFilePreviewAvailability("notes.txt");
  expect(ui.model.resolveFilePreviewAvailability("notes.txt")).toBe(first);
  result.resolve(true);
  expect(await first).toBe(true);
  expect(fetchFilePreviewAvailability).toHaveBeenCalledOnce();
});

it("rejects old contents that finish after the permission context changes", async () => {
  const result = pending<FilePreviewPayload>(), ui = setup();
  vi.mocked(fetchFilePreview).mockReturnValueOnce(result.promise);
  const old = ui.model.filePreviews;
  const observed = old.load("notes.txt").catch(reason => reason);
  await act(async () => {});
  ui.change("access");
  result.resolve(payload);
  expect(await observed).toEqual(new Error("File preview context changed"));
  expect(old.peek("notes.txt")).toBeUndefined();
  expect(await ui.model.filePreviews.load("notes.txt")).toBe(payload);
  expect(fetchFilePreview).toHaveBeenCalledTimes(2);
});

it("rejects metadata that finishes after its scope changes", async () => {
  const result = pending<FileReferenceMetadata>(), ui = setup();
  vi.mocked(fetchFileReferenceMetadata).mockReturnValueOnce(result.promise);
  const observed = ui.model.fileActions.resolveMetadata("notes.txt").catch(reason => reason);
  ui.change("scope");
  result.resolve({ path: payload.path, relative_path: "notes.txt" });
  expect(await observed).toEqual(new Error("File preview context changed"));
});

it("does not publish a positive probe after its scope changes", async () => {
  const result = pending<boolean>(), ui = setup();
  vi.mocked(fetchFilePreviewAvailability).mockReturnValueOnce(result.promise);
  const observed = ui.model.resolveFilePreviewAvailability("notes.txt");
  ui.change("scope");
  result.resolve(true);
  expect(await observed).toBe(false);
  expect(await ui.model.resolveFilePreviewAvailability("notes.txt")).toBe(true);
  expect(fetchFilePreviewAvailability).toHaveBeenCalledTimes(2);
});

it("keeps the logical pane and dirty confirmation when a temporary chat is admitted", () => {
  const ui = setup(true), action = vi.fn();
  act(() => { ui.model.setBrowserDirty(true); });
  act(() => { ui.model.guardPreview(action); });
  const confirmation = ui.model.pendingPreviewAction;
  ui.change("temporary");
  expect(ui.model.pendingPreviewAction).toBe(confirmation);
  act(() => { confirmation?.(); });
  expect(action).toHaveBeenCalledOnce();
});
