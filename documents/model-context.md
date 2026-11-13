# Model context and long-running work

## Harness contracts and prompt caching

The stable system prefix contains framework identity, tool contracts and the selected Router or Worker contract before editable Home and Project profiles. Tool catalogs have deterministic ordering and are selected separately for each role. PTC wraps the same selected catalog. Runtime role checks and the Router's direct-work budget apply to nested calls as well as native calls; prompt additions cannot expand these capabilities. The per-run budget counts ordinary task execution, including read-only investigation. Coordination, `runtime.check` and `memory.checkpoint` remain available after exhaustion; PTC also exposes these operations directly. Budget use and exhaustion do not rewrite tool schemas or the system prefix between model rounds.

Settings → Personality appends shared and role-specific system instructions. The runner captures these settings once per turn, so a save during generation does not change that turn's later requests or compaction rebuilds. The next turn reads the saved values. Editing a system prompt intentionally changes the request prefix; ordinary clock, memory and task-state updates enter fresh input snapshots rather than rewriting prior messages. Archived summaries are historical evidence, not new instructions or authorization. Internal maintenance uses a separate contract and treats profile text as reference data.

These choices preserve unchanged prefixes for provider caching. Actual reuse depends on the endpoint; the usage display uses reported cache metrics rather than assuming a cache hit.

Goal execution and continuation retain these role boundaries. A Router Goal does not grant permission to execute medium or large work directly; its runtime guidance requires durable Worker delegation too.

## Reasoning history

Each model configuration has a **Reasoning history** setting. Automatic follows the known endpoint's plaintext reasoning rules. Preserve keeps plaintext reasoning where the adapter permits it; Omit excludes it from compatible replay. Signed thinking blocks and opaque provider continuation state remain owned by the native adapter and are not converted to ordinary replies.

DeepSeek tool requests require complete reasoning replay, including earlier turns without tool calls. Cirno rejects Omit for those requests. Internal DeepSeek finalization retains tool schemas with tool selection disabled so the endpoint can reuse reasoning while generating the final answer. Without tools, DeepSeek ignores historical reasoning; the local estimate excludes that ignored history. This distinction follows the [DeepSeek thinking API contract](https://api-docs.deepseek.com/guides/thinking_mode/). Generating reasoning still consumes output tokens even when a later request does not reuse it. A relay or custom model can have different rules; choose a compatible policy for that endpoint.

The saved transcript retains reasoning independently of request filtering. Changing the policy does not delete it. Provider-reported usage calibrates the display after requests finish. During generation, context usage is an explicitly marked estimate that grows with reasoning, text and tool output; it is not an additional billing measurement.

The session also retains a content-free snapshot of the eight most recent completed provider requests, without waiting for the entire agent turn to finish. The context popover restores these input/output, cache and timing details after a page refresh, even when the relevant chat messages are outside the loaded history page. A request still generating has no final usage yet; its actual details become available when the provider returns. These snapshots are display metadata and are never added to model prompts.

Workers stream ordinary assistant updates between tool rounds. Their role prompt distinguishes these user-facing milestones from private reasoning and coordination reports. A complete response containing both prose and tool calls is also delivered before tool execution when a provider returns it without content deltas; already-streamed text is not repeated. Models still decide what content to generate, so this does not synthesize progress messages or force extra model requests.

## Checkpoints and compaction

Settings → Context consolidation separates the active input threshold, idle trigger/retention and checkpoint generation. The active threshold is a percentage of the selected model's window, capped by the safe input budget after reserving output space. It is checked between model requests, not by interrupting an active stream.

The configured maximum output is a ceiling, not a permanently reserved slice of context. With window `C`, configured maximum output `M`, output headroom `R = min(M, ceil(C × reserve%))` and safety margin `S = 1024`, the active input threshold is `min(C × active%, C − R − S)`. Settings → Context consolidation exposes the output headroom percentage (default 5%). Each request uses at most `min(M, C − measured input − S)` output tokens. After compaction that limit is recalculated; the saved model configuration stays unchanged. Normal requests, fallback models and checkpoint generation share this budget policy. Native Codex requests use the same headroom to trigger provider compaction; the Codex endpoint owns its output contract.

Responses server compaction and Codex pre-request compaction retain their native
90% trigger, capped by that same input budget. Both use the configured output
headroom percentage rather than reserving the full output ceiling.

When the next request extends the previous measured input, Cirno adds the estimated new messages to the provider's reported input count and compares that result with the full local estimate. Rewritten requests are measured afresh. This keeps appended replies and tool results in the budget even when the local tokenizer underestimates the accepted prefix.

For a 512,000-token window and 256,000-token output ceiling, default active compaction begins at 485,376 input tokens. At 300,000 input tokens the request may generate at most 210,976 tokens. Setting the output ceiling equal to the context window therefore does not collapse the usable input window to zero.

Checkpoint generation has its own output budget and reasoning effort. The budget includes both reasoning and checkpoint text and cannot exceed the conversation model's output budget. The default is at most 8,192 tokens and low effort; the provider may map effort values to its supported choices. Inherit follows the conversation's effort.

Before reaching the active input budget, the runner can append a system-origin checkpoint reminder. Its percentage is configurable; the default is 85% of that input budget. It asks the model to save its authorized task, verified results, hypotheses, blockers, next action and exact artifact references through the existing task-checkpoint tool. This is a reminder, not a guarantee that the model will call a tool, and it never grants authorization for new work. Internal maintenance requests do not receive this reminder because they do not own execution-task checkpoints.

Compaction keeps the accepted prefix separate from unsent output and tool results. Only the prefix is replaced; the latest delta stays in the next request. A replacement becomes active after the complete request, including its pending delta, passes the input budget check. Failed or cancelled preparation retains the previous summary and accepted history. A model checkpoint contains Task, State and Next sections. Reasoning and attempted tool calls are unverified evidence, not proof that an operation succeeded. Empty or `(nothing)` output is not allowed to erase a task handoff. Reasoning/tool-bearing input also requires the working-state headings.

If the provider fails, reaches its output limit, produces an invalid handoff or cannot fit the checkpoint request, Cirno retains a bounded evidence checkpoint instead. It preserves the original objective and recent state, including plaintext reasoning and tool arguments. The Web UI explicitly labels this as an evidence checkpoint rather than a normal model summary. Complete evidence stays archived. A bounded checkpoint is necessarily selective; exact research claims should be checked against source artifacts and verified results.

When an endpoint drops reasoning, the compaction request includes a separately labelled, unverified excerpt solely for checkpoint generation. The excerpt uses the input budget left after the accepted transcript and tool schemas; it retains the beginning and latest working notes when the full reasoning cannot fit. Complete source evidence stays archived. It is not rewritten into ordinary user-facing messages or treated as verified knowledge. Model switches and compaction can change cache reuse; unchanged prefixes and saved snapshots avoid routine history rewrites.

Tool output storage runs outside the shared event loop. A storage failure is
reported after the completed results are saved to the recovery checkpoint.
Continue replays those results instead of executing the completed calls again.
Stopping during output storage waits for its checkpoint to settle.

## Progress and interrupted output

Regular conversations stream ordinary assistant progress before tool work and show those updates outside the folded tool/reasoning activity. The Router sends user-visible progress through `user.message`; its internal text and execution details stay folded by default. Prompts request concise updates before substantial work and at meaningful milestones, without forwarding every tool result.

A continuously reasoning request cannot be made to produce a truthful progress report merely by a browser timer. Progress must be generated by the model. Reasoning-only responses are retained during length recovery and empty-answer retries, including when recovery limits are reached, so Continue can use saved work rather than starting without it. This preserves returned text and state; it does not recreate a provider's hidden computation.

Output-limit recovery distinguishes streamed Worker prose from Router internal text
and discarded tool calls. A length-limited response executes none of its tool calls,
including calls whose arguments happen to look complete. Recovery asks for new,
complete calls, preserves successful effects from earlier responses, and never
labels unsent Router text as already delivered. Router replies should resume as
short, complete `user.message` calls. This guidance is appended only after
truncation within the existing sequential recovery loop; it adds no concurrent
request and does not rewrite the reusable prompt prefix.

## Visual inputs

`files.view_image` adds a local image to the next model request as actual visual content. It shares filesystem permissions, size limits and image conversion with `files.read`; it does not run OCR or pass only a filename. The configured model must support image input. Images are excluded from persisted inline payloads while file references remain available for later reads.

New model setup tests image and native video input using small semantic samples. Accepting the request alone is not a positive result: the response must identify the sample. Authentication failures, timeouts and inconclusive replies remain unverified, with details available from **Test capabilities**. Model settings also let the owner explicitly choose Supported, Unsupported or Automatic / unverified. Declared unsupported visual inputs fail visibly without silently removing media. Native video probing uses the OpenAI-compatible `video_url` transport; other selected request APIs remain unverified for native video. This is distinct from reading extracted video frames as images.

### Independent learning failures and cache boundaries

Context consolidation treats the task checkpoint as the continuation requirement. Optional memory/Skill learning can fail without preventing that checkpoint from being saved. The notice records which updates completed, which remain incomplete, their error and the immutable source ID. Memory can replay saved writes without an API request; `/consolidate retry [source-id]` explicitly retries one retained batch in the original conversation. It never replaces the current task checkpoint. All retries are serial.

`agents.defaults.consolidation.max_retries` sets additional generation attempts (default 1, 0–10); zero disables extra attempts. Provider network retries are configured separately. Learning failures do not automatically regenerate a usable checkpoint.

The system/developer prefix stays unchanged during compaction; the checkpoint is a subsequent history message. The replaced history naturally loses its old exact-prefix cache match, while stable policy remains reusable. Compare provider-reported cache hits and misses to assess real cost; structural prefix tests alone cannot measure a proxy's billing behavior.

Ordinary findings always have batch provenance when no specific input-memory source is selected. Legacy model-written archive quotations do not block their save and are not recorded as exact evidence. Previously failed quote-only batches can be replayed through Memory or `/consolidate retry` without regenerating their checkpoint or making another model request. First consolidation after an upgrade may reuse an old checkpoint and surface that old batch's retained failure until recovery completes.

`/consolidate retry [source-id]` is advertised as an argument-taking side-channel command, so both the composer and message history highlight its command name. Results appear as localized consolidation reports, including on refresh. Reports show acknowledged saved items and pending items, distinguish replay from a new model invocation, retain the source ID and confirm that the existing checkpoint is unchanged. Original proposals shown after regeneration are not a list of saved memories; an empty extraction explicitly reports zero saved updates.

## Owner-selected context

Settings → Skills can pin installed, enabled and available Skills for full injection in Router/Worker prompts. This also covers transient Worker subagents, but excludes owner pins from maintenance contracts. Existing author-declared `always` Skills retain their behavior. Skill names are sorted before injection, avoiding cache changes caused by selection order.

Settings → Memory library can pin extra `memory/` text files with a separate shared token budget. The MEMORY.md snapshot and those excerpts form one versioned input snapshot: identical content adds nothing; edits or removing a selection append a fresh snapshot without modifying old messages. Settings are reread before fresh-input preparation, so the first turn after saving receives the new selection. System prompt changes remain explicit owner actions; ordinary memory edits preserve that prefix.
