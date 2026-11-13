import { useMemo } from "react";
import { UserMessageText } from "@/components/UserMessageText";
import { SlashCommandText } from "@/components/SlashCommandText";
import {
  INLINE_REFERENCE_HIGHLIGHT_COLOR,
  InlineTokenHighlight,
} from "@/components/InlineTokenHighlight";
import { matchingSlashCommand } from "@/lib/slash-command";
import type { MessageBubbleProps } from "../contracts";
import {
  mergeCliMentionApps,
  mergeMcpMentionPresets,
} from "../model/mentionCatalog";

export function UserText({
  text,
  message,
  cliApps = [],
  mcpPresets = [],
  slashCommands = [],
}: MessageBubbleProps & { text: string }) {
  const apps = useMemo(
    () => mergeCliMentionApps(cliApps, message.cliApps),
    [cliApps, message.cliApps],
  );
  const presets = useMemo(
    () => mergeMcpMentionPresets(mcpPresets, message.mcpPresets),
    [mcpPresets, message.mcpPresets],
  );
  const command = matchingSlashCommand(text, slashCommands),
    commandPrefix = command ? /^(\s*)(\/\S+)/.exec(text) : null,
    bang = /^(\s*)!/.exec(text);
  if (bang)
    return (
      <>
        {bang[1]}
        <InlineTokenHighlight
          testId="message-shell-prefix"
          className="font-normal"
          color={INLINE_REFERENCE_HIGHLIGHT_COLOR}
        >
          <span className="opacity-90">!</span>
        </InlineTokenHighlight>
        {text.slice(bang[0].length)}
      </>
    );
  return (
    <>
      {commandPrefix && <>{commandPrefix[1]}<SlashCommandText command={commandPrefix[2]} /></>}
      <UserMessageText
        text={commandPrefix ? text.slice(commandPrefix[0].length) : text}
        cliApps={apps}
        mcpPresets={presets}
        sessionMentions={message.sessionMentions}
      />
    </>
  );
}
