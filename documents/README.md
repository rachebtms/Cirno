# Cirno documentation

These guides describe the current Cirno implementation. The Python gateway owns execution, durable conversations, tools and memory; the browser displays and controls that state.

## Use Cirno

- [Install, run and configure](configuration.md)
- [Configuration](configuration.md): model providers, settings, channels, Projects and Nodes.
- [Docker deployment and publishing](docker.md): local builds, image publication and persistent data.
- [Home and workspaces](home-and-workspaces.md): profiles, storage and working directories.
- [Goals and coordination](goals-and-dream.md): sustained work, delegation, heartbeat and Skills.
- [Notification inbox](notification-inbox.md): action requests, conversation reports and system notices.

## Behavior and architecture

- [Memory](architecture/memory.md): BM25, evidence, scopes, Dream and optional embeddings.
- [Asynchronous questions](architecture/async-questions.md): queued questions and steering replies.
- [Programmatic tool calling](architecture/ptc.md): PTC execution and conversation reply delivery.
- [Tool namespaces](architecture/tools.md): logical names, native function names and role selection.
- [Conversation routing and Stop](development/conversation-routing.md): isolation and cancellation.

## Develop Cirno

- [Source layout](development/source-layout.md)
- [Contributing](development/contributing.md)
- [Example configuration](examples/config.json)

Historical reviews, benchmark runs and earlier implementations are local archive material under ignored `references/`. They are not current product documentation or bundled Agent guidance. Third-party license text remains in its original form.

## Release notes

- [0.1.1](releases/0.1.1.md): browser setup, conversation and Goal fixes, and inbox behavior.
