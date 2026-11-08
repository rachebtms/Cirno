import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { openPopover } from "@/tests/settings-test-utils";
import { describe, expect, it, vi } from "vitest";
import { Modal, toast } from "@heroui/react";
import { useEditCompletion, type EditCompletion } from "@/features/settings/shared/useEditCompletion";
import { NumberInput } from "@/features/settings/shared/SettingsControls";
import { ReasoningEffortPicker } from "@/features/settings/models/ReasoningEffortPicker";
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((done) => { resolve = done; });
    return { promise, resolve };
}
function Editor({ save, identity = "a", expose }: {
    save: (identity: string, value: string) => Promise<boolean>;
    identity?: string;
    expose?: (edits: EditCompletion) => void;
}) {
    const [value, setValue] = useState("");
    const edits = useEditCompletion(value, value !== "", () => save(identity, value), value !== "invalid", identity);
    expose?.(edits);
    return <div onChangeCapture={edits.onChangeCapture} onFocusCapture={edits.onFocusCapture} onBlurCapture={edits.onBlurCapture}>
    <input aria-label="Draft" value={value} onChange={(event) => setValue(event.target.value)}/>
    <button onClick={() => setValue("selected")}>Select</button>
    <button onClick={() => void edits.commit()}>Close</button>
  </div>;
}
describe("settings edit completion", () => {
    it("does not restore a closing picker over a newer focused input", async () => {
        render(<Modal.Backdrop isOpen><Modal.Container><Modal.Dialog><Modal.Header><Modal.Heading>Model</Modal.Heading></Modal.Header><Modal.Body>
        <ReasoningEffortPicker token="test" provider={undefined} model="test" value="" onChange={() => { }}/>
        <input aria-label="Next field"/>
      </Modal.Body></Modal.Dialog></Modal.Container></Modal.Backdrop>);
        const effort = screen.getByRole("combobox", { name: "Reasoning effort" });
        await openPopover(screen.getByRole("button", { name: "Show suggestions Reasoning effort" }));
        await openPopover(await screen.findByRole("option", { name: "Default" }));
        await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
        await waitFor(() => expect(effort).toHaveFocus());
        const next = screen.getByRole("textbox", { name: "Next field" });
        next.focus();
        await act(async () => { });
        expect(next).toHaveFocus();
    });
    it("reports an exception from saving, retains the draft and permits retry", async () => {
        const notice = vi.spyOn(toast, "danger").mockReturnValue("save-error");
        const save = vi.fn().mockRejectedValueOnce(new Error("Storage unavailable")).mockResolvedValue(true);
        let edits!: EditCompletion;
        render(<Editor save={save} expose={current => { edits = current; }}/>);
        fireEvent.focus(screen.getByRole("textbox"));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "research parameters" } });
        await act(async () => { expect(await edits.commit()).toBe(false); });
        expect(notice).toHaveBeenCalledExactlyOnceWith("Storage unavailable", { timeout: 0 });
        expect(screen.getByRole("textbox")).toHaveValue("research parameters");
        await act(async () => { expect(await edits.commit()).toBe(true); });
        expect(save).toHaveBeenCalledTimes(2);
        notice.mockRestore();
    });
    it("keeps text draft through pauses, then deduplicates blur and close", async () => {
        const pending = deferred<boolean>();
        const save = vi.fn(() => pending.promise);
        render(<Editor save={save}/>);
        const input = screen.getByRole("textbox");
        fireEvent.focus(input);
        fireEvent.change(input, { target: { value: "first" } });
        await act(async () => { await new Promise((done) => setTimeout(done, 700)); });
        expect(save).not.toHaveBeenCalled();
        fireEvent.change(input, { target: { value: "latest" } });
        fireEvent.blur(input);
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await waitFor(() => expect(save).toHaveBeenCalledWith("a", "latest"));
        expect(save).toHaveBeenCalledTimes(1);
        await act(async () => pending.resolve(true));
    });
    it("saves discrete edits immediately and serializes later completed drafts", async () => {
        const first = deferred<boolean>();
        const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
        render(<Editor save={save}/>);
        fireEvent.click(screen.getByRole("button", { name: "Select" }));
        await waitFor(() => expect(save).toHaveBeenCalledWith("a", "selected"));
        expect(save).toHaveBeenCalledTimes(1);
        const input = screen.getByRole("textbox");
        fireEvent.focus(input);
        fireEvent.change(input, { target: { value: "second" } });
        fireEvent.blur(input);
        await act(async () => { });
        expect(save).toHaveBeenCalledTimes(1);
        await act(async () => first.resolve(true));
        await waitFor(() => expect(save).toHaveBeenLastCalledWith("a", "second"));
    });
    it("does not confuse a later edit with an earlier successful draft containing the same text", async () => {
        const pending = deferred<boolean>();
        const save = vi.fn().mockResolvedValueOnce(true).mockReturnValueOnce(pending.promise).mockResolvedValue(true);
        render(<Editor save={save}/>);
        fireEvent.click(screen.getByRole("button", { name: "Select" }));
        await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
        const input = screen.getByRole("textbox");
        fireEvent.change(input, { target: { value: "different" } });
        fireEvent.blur(input);
        await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
        fireEvent.change(input, { target: { value: "selected" } });
        fireEvent.blur(input);
        await act(async () => pending.resolve(true));
        await waitFor(() => expect(save).toHaveBeenCalledTimes(3));
        expect(save).toHaveBeenLastCalledWith("a", "selected");
    });
    it("flushes the focused version on unmount, including after a request already in flight", async () => {
        const first = deferred<boolean>();
        const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
        const view = render(<Editor save={save}/>);
        fireEvent.click(screen.getByRole("button", { name: "Select" }));
        await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
        fireEvent.focus(screen.getByRole("textbox"));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "unmounted" } });
        view.unmount();
        await act(async () => first.resolve(true));
        await waitFor(() => expect(save).toHaveBeenLastCalledWith("a", "unmounted"));
    });
    it("persists a revert to the old baseline when an earlier save is still pending", async () => {
        const first = deferred<boolean>();
        const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
        render(<Editor save={save}/>);
        fireEvent.click(screen.getByRole("button", { name: "Select" }));
        await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "" } });
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await act(async () => first.resolve(true));
        await waitFor(() => expect(save).toHaveBeenLastCalledWith("a", ""));
    });
    it("retains an empty numeric draft instead of committing it as zero", async () => {
        const save = vi.fn().mockResolvedValue(true);
        function NumericEditor() {
            const [value, setValue] = useState(1);
            const edits = useEditCompletion(value, value !== 1, () => save(value), Number.isFinite(value));
            return <div onChangeCapture={edits.onChangeCapture} onFocusCapture={edits.onFocusCapture} onBlurCapture={edits.onBlurCapture}>
        <NumberInput value={value} min={0} max={2} onChange={setValue}/>
      </div>;
        }
        render(<NumericEditor />);
        const input = screen.getByRole("spinbutton");
        fireEvent.focus(input);
        fireEvent.change(input, { target: { value: "" } });
        fireEvent.blur(input);
        await act(async () => { });
        expect(input).toHaveValue(null);
        expect(save).not.toHaveBeenCalled();
        fireEvent.change(input, { target: { value: "0" } });
        fireEvent.blur(input);
        await waitFor(() => expect(save).toHaveBeenCalledWith(0));
    });
    it("blocks completion for invalid or rejected drafts and permits retry", async () => {
        const save = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
        let edits!: EditCompletion;
        render(<Editor save={save} expose={(current) => { edits = current; }}/>);
        fireEvent.focus(screen.getByRole("textbox"));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "invalid" } });
        expect(await edits.commit()).toBe(false);
        expect(save).not.toHaveBeenCalled();
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "valid" } });
        expect(await edits.commit()).toBe(false);
        expect(screen.getByRole("textbox")).toHaveValue("valid");
        expect(await edits.commit()).toBe(true);
        expect(save).toHaveBeenCalledTimes(2);
    });
    it("does not flush a newer focused text draft when a discrete save finishes", async () => {
        const first = deferred<boolean>();
        const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
        render(<Editor save={save}/>);
        fireEvent.click(screen.getByRole("button", { name: "Select" }));
        await waitFor(() => expect(save).toHaveBeenCalledWith("a", "selected"));
        fireEvent.focus(screen.getByRole("textbox"));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "still typing" } });
        await act(async () => first.resolve(true));
        expect(save).toHaveBeenCalledTimes(1);
        fireEvent.blur(screen.getByRole("textbox"));
        await waitFor(() => expect(save).toHaveBeenLastCalledWith("a", "still typing"));
    });
    it("retains each source object when blur and an object switch share a turn", async () => {
        const first = deferred<boolean>();
        const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
        let edits!: EditCompletion;
        const view = render(<Editor save={save} expose={(current) => { edits = current; }}/>);
        fireEvent.focus(screen.getByRole("textbox"));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "object-a" } });
        fireEvent.blur(screen.getByRole("textbox"));
        view.rerender(<Editor save={save} identity="b" expose={(current) => { edits = current; }}/>);
        fireEvent.focus(screen.getByRole("textbox"));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "object-b" } });
        const completion = edits.commit();
        await waitFor(() => expect(save).toHaveBeenCalledWith("a", "object-a"));
        await act(async () => first.resolve(true));
        expect(await completion).toBe(true);
        expect(save).toHaveBeenLastCalledWith("b", "object-b");
    });
});
