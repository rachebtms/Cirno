# Cirno documentation

These guides describe the current Cirno implementation. The Python service owns execution, durable conversations, tools and memory; the browser displays and controls that state.

## Use Cirno

- [Configuration](configuration.md): model providers, settings, channels, Projects and Nodes.
- [Docker deployment and publishing](docker.md): local builds, image publication and persistent data.
- [Home and workspaces](home-and-workspaces.md): profiles, storage and working directories.
- [Goals and coordination](goals-and-dream.md): sustained work, delegation, heartbeat and Skills.
- [Notification inbox](notification-inbox.md): action requests, conversation reports and system notices.
- [Instance migration](migrations.md): automatic 0.1.6 import, retained originals and interrupted-startup recovery.
- [Backup and restore](backups.md): complete instance archives, extra directories and restoration.
- [Conversation input commands](commands.md): complete command catalog, v0.1.6 compatibility and conversation restrictions.
- [Model context and long-running work](model-context.md)
- [Memory retrieval](memory-retrieval.md)

## Behavior and architecture

- [Memory](architecture/memory.md): BM25, evidence, scopes, context consolidation and optional embeddings.
- [Asynchronous questions](architecture/async-questions.md): queued questions and steering replies.
- [Programmatic tool calling](architecture/ptc.md): PTC execution and conversation reply delivery.
- [Operation review](architecture/access-review.md): permission modes, independent AI review and owner decisions.
- [Tool namespaces](architecture/tools.md): logical names, native function names and role selection.
- [Conversation routing and Stop](development/conversation-routing.md): isolation and cancellation.

## Develop Cirno

- [Source layout](development/source-layout.md)
- [Contributing](development/contributing.md)
- [API versions](development/api.md): v0 endpoints, transport and authentication.
- [Example configuration](examples/config.json)

Historical reviews, benchmark runs and earlier implementations are local archive material under ignored `references/`. They are not current product documentation or bundled Agent guidance. Third-party license text remains in its original form.

## Release notes

- [0.2.16](releases/0.2.16.md): complete command discovery and compatibility, expanded memory cloud, waiting Worker supervision, compact Goal reminders and correlated execution reports.

- [0.2.15](releases/0.2.15.md): actionable memory/checkpoint revision conflicts, explicit rejected-write results, and native/PTC persistence checks.

- [0.2.14](releases/0.2.14.md): fixed Skills and memory file injection, credential visibility controls, Router supervision and reply recovery, and Setup version-constraint checks.

- [0.2.13](releases/0.2.13.md): reliable legacy learning recovery, highlighted retry commands and localized consolidation reports with confirmed save details.

- [0.2.12](releases/0.2.12.md): independent checkpoint and learning outcomes, stable prompt prefixes, recoverable learning and configurable sequential retries.

- [0.2.11](releases/0.2.11.md): reliable SSH job recovery and monitoring, grounded consolidation retries, memory loading controls and unlimited setup deadlines.

- [0.2.10](releases/0.2.10.md): reliable automatic saves, restart-state tracking and restored settings controls.
- [0.2.9](releases/0.2.9.md): complete setup catalogue verification, additional optional tools and mobile message editing fixes.
- [0.2.8](releases/0.2.8.md): unified container image, command-selected persistent dependencies and standard uv/npm/browser tool environments.

- [0.2.7](releases/0.2.7.md): consolidation retry and journal recovery fixes, revision-safe memory links, retrieval deadlines and a smaller full-image toolset.

- [0.2.6](releases/0.2.6.md): unified context consolidation and Skill learning, memory cloud search, credential privacy, bounded embedding retrieval and long-task recovery fixes.

- [0.2.5](releases/0.2.5.md): mobile keyboard visibility, automatic settings saving, model icon alignment and bundled full-image Python libraries.
- [0.2.4](releases/0.2.4.md): role-specific execution contracts, editable system prompts, cache-aware context and memory scope/integrity fixes.
- [0.2.3](releases/0.2.3.md): system input delivery and project-wide bug fixes.
- [0.2.2](releases/0.2.2.md): context budgeting, SSH startup environments, visual input checks and Router heartbeat controls.
- [0.2.1](releases/0.2.1.md): conversational first setup, Router profile and delegation fixes, question cancellation, Trace export and layout fixes.
- [0.2.0](releases/0.2.0.md): tabbed workspace, local/SSH terminals, request transparency, encrypted credentials and long-task reliability fixes.
- [0.1.6](releases/0.1.6.md): reliable delegated reports, retryable backup recovery, browser-session revocation and inline message editing.
- [0.1.5](releases/0.1.5.md): recoverable long-task context, external embeddings, complete backups and supervisor controls.
- [0.1.4](releases/0.1.4.md): mobile recovery, workspace and AI review settings, MCP editing, remote installation and persistent full images.
- [0.1.3](releases/0.1.3.md): package boundaries, instance storage, account passwords, conversation controls and independent operation review.
- [0.1.2](releases/0.1.2.md): useful Overview shortcuts and removal of obsolete migration and compatibility paths.
- [0.1.1](releases/0.1.1.md): browser setup, conversation and Goal fixes, and inbox behavior.

- [Tabbed workspace, terminals, event inspection and credentials](workspace.md)

- [Environment setup](setup.md): namespaced components, personal presets and unified container provisioning.
