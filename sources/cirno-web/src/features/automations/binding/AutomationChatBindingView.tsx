import {
  Button,
  Label,
  ListBox,
  Modal,
  Select,
  TextArea,
  TextField,
} from "@heroui/react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { AutomationChat } from "@/lib/contracts/automations";
import { ChatIdentity } from "./ChatIdentity";
import { useChatBinding, type ChatBindingProps } from "./useChatBinding";
import { InlineError } from "@/ui/feedback/InlineError";
export type {
  AutomationChatNames,
  ChangeAutomationChat,
} from "./useChatBinding";

export function AutomationChatBindingView({
  children,
  ...props
}: ChatBindingProps & { children: (picker: ReactNode) => ReactNode }) {
  const { t } = useTranslation();
  const state = useChatBinding(props);
  const { job, data, showBrandLogos, loadError, onReload } = props;
  const {
    tx,
    draft,
    setDraft,
    current,
    saved,
    fallback,
    saving,
    error,
    locked,
    pickerDisabled,
    targetUnavailable,
    chatTitle,
  } = state;
  const identity = (chat: AutomationChat) => (
    <ChatIdentity
      chat={chat}
      title={chatTitle(chat)}
      showBrandLogos={showBrandLogos}
    />
  );
  const selected = draft?.target ?? current ?? fallback;
  const picker = (
    <Select
      value={selected.id}
      isDisabled={pickerDisabled}
      onChange={(id) => {
        if (id !== null) state.select(String(id));
      }}
      className="automation-chat-select"
    >
      <Label>{tx(draft ? "new" : "label")}</Label>
      <Select.Trigger
        ref={draft ? undefined : state.trigger}
        aria-busy={
          !loadError && (!data || data.revision !== job.chat_binding_revision)
        }
      >
        <Select.Value>{identity(selected)}</Select.Value>
        <Select.Indicator />
      </Select.Trigger>
      <Select.Popover>
        <ListBox aria-label={tx(draft ? "new" : "label")}>
          {!current && (
            <ListBox.Item id="current" isDisabled textValue={fallback.title}>
              {identity(fallback)}
            </ListBox.Item>
          )}
          {data?.chats.map((chat) => (
            <ListBox.Item
              key={chat.id}
              id={chat.id}
              textValue={`${chatTitle(chat)} ${chat.channel}`}
              isDisabled={
                chat.unavailable || (!!draft && chat.id === current?.id)
              }
            >
              {identity(chat)}
              <ListBox.ItemIndicator />
            </ListBox.Item>
          ))}
        </ListBox>
      </Select.Popover>
    </Select>
  );
  if (!draft)
    return children(
      <section className="automation-chat-binding">
        {picker}
        <p role={saved ? "status" : undefined} className="automation-hint">
          {tx(
            job.state.pending ? "busy" : saved ? "saved" : "hint",
            saved ? { chat: chatTitle(saved.target) } : undefined,
          )}
        </p>
        {saved &&
          current?.id === saved.target.id &&
          data?.chats.some(
            (chat) => chat.id === saved.previous.id && !chat.unavailable,
          ) && (
            <Button
              variant="ghost"
              size="sm"
              isDisabled={pickerDisabled}
              onPress={() =>
                setDraft({
                  target: saved.previous,
                  previous: current,
                  revision: data.revision,
                  message: job.payload.message,
                })
              }
            >
              {tx("changeBack", { chat: chatTitle(saved.previous) })}
            </Button>
          )}
        <InlineError message={loadError} />
        {loadError && (
          <Button variant="secondary" size="sm" onPress={onReload}>
            {tx("retry")}
          </Button>
        )}
        {data && data.chats.length <= (current ? 1 : 0) && (
          <p className="automation-hint">{tx("available")}</p>
        )}
      </section>,
    );
  return (
    <>
      <Modal.Header>
        <Modal.Heading ref={state.heading} tabIndex={-1}>
          {tx("change")}
        </Modal.Heading>
        <Modal.CloseTrigger isDisabled={saving} />
      </Modal.Header>
      <Modal.Body>
        <div
          className="automation-binding-previous"
          role="group"
          aria-label={tx("previous")}
        >
          <span>{tx("previous")}</span>
          {identity(draft.previous)}
        </div>
        {picker}
        <p>{tx("effect")}</p>
        <p className="automation-hint">{tx("history")}</p>
        {draft.editingMessage ? (
          <TextField
            value={draft.message}
            onChange={(message) => setDraft({ ...draft, message })}
            isDisabled={saving}
          >
            <Label>{tx("message")}</Label>
            <TextArea rows={4} autoFocus />
            <p className="automation-hint">{tx("editInstructionsHint")}</p>
          </TextField>
        ) : (
          <section className="automation-binding-message">
            <div className="automation-command-heading">
              <span>{tx("message")}</span>
              <Button
                variant="ghost"
                size="sm"
                isDisabled={saving}
                onPress={() => setDraft({ ...draft, editingMessage: true })}
              >
                {tx("editInstructions")}
              </Button>
            </div>
            <p>{draft.message}</p>
          </section>
        )}
        <p className="automation-hint">{tx("review")}</p>
      </Modal.Body>
      <Modal.Footer className="automation-dialog-footer">
        <InlineError
          message={error || (targetUnavailable ? tx("unavailable") : null)}
        />
        <div className="automation-dialog-actions">
          <Button variant="ghost" isDisabled={saving} onPress={state.back}>
            {t("settings.automations.cancel")}
          </Button>
          <Button
            isDisabled={locked || targetUnavailable || !draft.message.trim()}
            isPending={saving}
            onPress={() => {
              void state.save();
            }}
          >
            {tx(draft.editingMessage ? "saveAndChange" : "confirm")}
          </Button>
        </div>
      </Modal.Footer>
    </>
  );
}
