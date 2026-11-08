import type { WebUIMutationTransport } from "@/lib/api";
import { useTelegramBinding } from "./model/useTelegramBinding";
import { useTelegramPairing } from "./model/useTelegramPairing";
import { TelegramAccount } from "./ui/TelegramAccount";
import { TelegramDelivery } from "./ui/TelegramDelivery";
import { TelegramLinks } from "./ui/TelegramLinks";
import "./telegram.css";
export function TelegramSettings({
  client,
  onConfigure,
}: {
  client: WebUIMutationTransport;
  onConfigure: () => void;
}) {
  const state = useTelegramBinding(client),
    pairing = useTelegramPairing(state),
    data = state.status.value;
  return (
    <div className="telegram-settings">
      <TelegramAccount
        binding={state}
        pairing={pairing}
        onConfigure={onConfigure}
      />
      {data && (
        <>
          <TelegramDelivery data={data} state={state} />
          <TelegramLinks state={state} value={data.webui_url} />
        </>
      )}
    </div>
  );
}
