import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "@heroui/react";
import { useLifetime } from "@/ui/resources/useLifetime";
import { isCapabilitySection, type SettingsExitGuard, type SettingsSectionKey } from "../contracts";
import type { EditCompletion } from "../shared/useEditCompletion";
import type { SettingsController } from "../useSettingsController";
export function useSettingsNavigation(controller: SettingsController, restartInProgress: boolean, registerExitGuard?: (guard: SettingsExitGuard | null) => void) {
    const { activeSection, selectSection: selectSectionNow } = controller;
    const isCurrent = useLifetime(controller.client);
    const intent = useRef(0);
    const [exit, setExit] = useState<{
        owner: unknown;
        leave: () => void;
    } | null>(null);
    const pendingExit = exit?.owner === controller.client ? exit.leave : null;
    const setPendingExit = (leave: (() => void) | null) => setExit(leave ? { owner: controller.client, leave } : null);
    const latestExitState = useRef({ requiresRestart: controller.requiresRestart, restartInProgress });
    latestExitState.current = { requiresRestart: controller.requiresRestart, restartInProgress };
    const channelCompletion = useRef<(() => Promise<boolean>) | null>(null);
    const registerChannelCompletion = useCallback((handler: (() => Promise<boolean>) | null) => {
        channelCompletion.current = handler;
    }, []);
    const editOwners = new Map<SettingsSectionKey, Pick<EditCompletion, "commit" | "needsCompletion">[]>([
        ["models", [controller.modelEdits]],
        ["advanced", [controller.safetyEdits]],
        ["capabilities", [controller.webEdits]],
    ]);
    const runtimeCompletion = useRef(controller.runtimeConfigState.completion);
    runtimeCompletion.current = controller.runtimeConfigState.completion;
    const latestEditOwners = useRef(editOwners);
    latestEditOwners.current = editOwners;
    const flushEdits = useCallback(async () => {
        const results = await Promise.all([
            ...[...latestEditOwners.current.values()].flat().map((edits) => edits.commit()),
            runtimeCompletion.current.commit(),
            channelCompletion.current?.() ?? true,
        ]);
        return results.every(Boolean);
    }, []);
    const needsCompletion = useCallback(() => {
        return Boolean(channelCompletion.current) || runtimeCompletion.current.needsCompletion() ||
            [...latestEditOwners.current.values()].flat().some((edits) => edits.needsCompletion());
    }, []);
    const navigate = useCallback((complete: (() => Promise<boolean>) | null, finish: (isValid: () => boolean) => void) => {
        if (!isCurrent())
            return;
        const id = ++intent.current;
        const isValid = () => isCurrent() && intent.current === id;
        setExit(null);
        if (!complete) {
            finish(isValid);
            return;
        }
        void complete().then(saved => { if (saved && isValid())
            finish(isValid); }).catch(reason => {
            if (isValid())
                toast.danger(reason instanceof Error ? reason.message : String(reason), { timeout: 0 });
        });
    }, [isCurrent]);
    const selectSection = (section: SettingsSectionKey) => {
        const owners = [...(editOwners.get(isCapabilitySection(activeSection) ? "capabilities" : activeSection) ?? []), runtimeCompletion.current];
        const channel = activeSection === "channels" ? channelCompletion.current : null;
        const complete = channel || owners.some(edits => edits.needsCompletion())
            ? async () => (await Promise.all([...owners.map(edits => edits.commit()), channel?.() ?? true])).every(Boolean)
            : null;
        navigate(complete, () => selectSectionNow(section));
    };
    const requestExit = useCallback<SettingsExitGuard>((leave, { promptRestart = true } = {}) => {
        navigate(needsCompletion() ? flushEdits : null, isValid => {
            const finishLeave = () => { if (isValid())
                leave(); };
            const current = latestExitState.current;
            if (promptRestart && current.requiresRestart() && !current.restartInProgress)
                setExit({ owner: controller.client, leave: finishLeave });
            else
                finishLeave();
        });
    }, [flushEdits, needsCompletion, navigate, controller.client]);
    useEffect(() => {
        registerExitGuard?.(requestExit);
        return () => registerExitGuard?.(null);
    }, [registerExitGuard, requestExit]);
    return { selectSection, requestExit, pendingExit, setPendingExit, registerChannelCompletion };
}
