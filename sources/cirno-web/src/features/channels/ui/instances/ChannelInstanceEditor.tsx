import { Button, Form } from "@heroui/react";
import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ChannelConfigField } from "@/channel-plugins/catalog";
import type { CirnoChannelInstanceInfo } from "@/lib/contracts/channels";
import { useRequest } from "@/ui/resources/useRequest";
import { useEditCompletion } from "@/features/settings/shared/useEditCompletion";
import { useChannelDraft } from "../../model/useChannelDraft";
import type { ChannelInstancesState } from "../../model/useChannelInstances";
import { ChannelFields } from "../fields/ChannelFields";
export function ChannelInstanceEditor({
  state,
  instance,
  fields,
}: {
  state: ChannelInstancesState;
  instance: CirnoChannelInstanceInfo;
  fields: ChannelConfigField[];
}) {
  const { t } = useTranslation(),
    owner = useMemo(
      () => ({ parent: state.owner, id: instance.id }),
      [state.owner, instance.id],
    ),
    scope = useRequest(owner);
  const draft = useChannelDraft(owner, fields, instance.config_values),
    snapshot = draft.snapshot;
  const save = async () => {
    if (!scope.isCurrent()) return false;
    if (!draft.dirty) return true;
    const saved = await state.save(instance, draft.payload);
    if (!saved || !scope.isCurrent()) return false;
    draft.ack(snapshot);
    return true;
  };
  const completion = useEditCompletion(
    draft.revision,
    draft.dirty,
    save,
    true,
    instance.id,
  );
  const { setCompletion } = state.selection;
  useEffect(() => {
    setCompletion(completion.commit);
    return () => setCompletion(null);
  }, [setCompletion, completion.commit]);
  return (
    <div
      onChangeCapture={completion.onChangeCapture}
      onFocusCapture={completion.onFocusCapture}
      onBlurCapture={completion.onBlurCapture}
    >
      <Form
        className="channel-instance-editor"
        onSubmit={(event) => {
          event.preventDefault();
          void completion.commit();
        }}
      >
        <ChannelFields
          fields={fields}
          values={draft.values}
          configuredFields={new Set(instance.configured_fields)}
          visibleSecrets={draft.visible}
          clearedSecrets={draft.cleared}
          onChange={draft.change}
          onToggleSecret={draft.toggleSecret}
          onClearSecret={(key, clear) => {
            completion.complete();
            draft.clearSecret(key, clear);
          }}
          secretActionsDisabled={state.mutation.busy}
          showSecretActions
          disabled={state.operation?.kind === "toggle"}
        />
        <Button
          type="submit"
          size="sm"
          variant="secondary"
          isPending={
            state.operation?.kind === "save" &&
            state.operation.id === instance.id
          }
          isDisabled={state.mutation.busy || !draft.dirty}
        >
          {t("settings.channels.saveSettings")}
        </Button>
      </Form>
    </div>
  );
}
