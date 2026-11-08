/** One-time migration of preview browser state; normal routing uses immutable IDs. */
import { ROUTER_SESSION_KEY as NEW, ROUTER_CHAT_ID } from "./conversation-role";
const OLD_KEYS = ["websocket:global", "websocket:cirno"];
const OLD_HANDLES = ["handle_335e48447b25d7e301b326b3db91c36c", "handle_552c2715056fede48f3b8ec505ba6f20"];
const NEW_HANDLE = "handle_9daf584999d74888c635d1df82976250";
function references(value: unknown, field = ""): unknown {
  if (Array.isArray(value)) return value.map(item => references(item, field));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [OLD_KEYS.includes(key) ? NEW : key, references(item, key)]));
  if (typeof value !== "string") return value;
  if (["id", "key", "activeKey", "sessionKey", "session_key", "chatId", "chat_id", "selected"].includes(field)) {
    if (OLD_HANDLES.includes(value)) return NEW_HANDLE;
    if (OLD_KEYS.includes(value)) return NEW;
    if (OLD_KEYS.some(key => value === `chat:${key}`)) return `chat:${NEW}`;
    if (["chat_id", "chatId"].includes(field) && ["global", "cirno"].includes(value)) return ROUTER_CHAT_ID;
  }
  return value;
}
export function migrateBrowserCirnoIdentity(storage?: Storage, location: Location = window.location): string[] {
  const errors: string[] = [];
  try {
    storage ??= localStorage;
    const keys = Array.from({ length: storage.length }, (_, index) => storage!.key(index)).filter((key): key is string => !!key && key.startsWith("cirno"));
    for (const key of keys) {
      try {
        const raw = storage.getItem(key);
        if (!raw || !OLD_KEYS.some(old => raw.includes(old) || key.includes(old)) && !OLD_HANDLES.some(old => raw.includes(old))) continue;
        const updated = JSON.stringify(references(JSON.parse(raw)));
        const target = OLD_KEYS.reduce((updated, old) => updated.replace(old, NEW), key);
        storage.setItem(target, updated);
        if (target !== key) storage.removeItem(key);
      } catch (reason) { errors.push(`Could not update saved conversation state (${key}): ${String(reason)}`); }
    }
  } catch (reason) { errors.push(`Could not read saved conversation state: ${String(reason)}`); }
  const hash = decodeURIComponent(location.hash);
  if (OLD_KEYS.some(old => hash === `#/chat/${old}`)) history.replaceState(null, "", `#/chat/${encodeURIComponent(NEW)}`);
  return errors;
}
