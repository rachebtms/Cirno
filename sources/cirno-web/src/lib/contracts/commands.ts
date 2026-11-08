/** Commands contracts shared by the browser and its transports. */

/**
 * Backend-owned contract for how a slash command affects WebUI turn state.
 *
 * - side_channel: returns control text without starting or ending an agent turn.
 * - finalize_active_turn: side-channel command that also closes the active UI turn.
 * - stop_active_turn: cancels the active turn; exact submits may be intercepted locally.
 * - agent_turn: always enters the normal agent path.
 * - agent_turn_with_args: no args is side-channel usage; args enter the agent path.
 */
export type SlashCommandLifecycle =
  | "side_channel"
  | "finalize_active_turn"
  | "stop_active_turn"
  | "agent_turn"
  | "agent_turn_with_args";

export interface SlashCommand {
  command: string;
  title: string;
  description: string;
  icon: string;
  argHint?: string;
  lifecycle: SlashCommandLifecycle;
  acceptsArgs: boolean;
}
