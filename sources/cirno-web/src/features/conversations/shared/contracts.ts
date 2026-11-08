export interface ConversationDeleteItem {
  key: string;
  label: string;
}
export type ConversationDeleteDecision = (confirmed: boolean) => void;
export interface ConversationDeleteActions {
  onRequestDelete: (
    key: string,
    label: string,
    onDecision?: ConversationDeleteDecision,
  ) => void;
  onRequestDeleteMany?: (
    items: ConversationDeleteItem[],
    onDecision?: ConversationDeleteDecision,
  ) => void;
}
