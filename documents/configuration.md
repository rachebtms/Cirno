# Configuration

`cirno webui --port 8000` prepares the local Web interface and starts or attaches to the gateway. Configure a provider in Settings → Models. An instance stores configuration in `~/.cirno/config.json`; select another Home with `cirno --home /path/to/home webui`.

## Install from a checkout

Requires Python 3.11+ and Node.js 24. From the repository root:

```sh
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
python -m pip install -e .
cirno webui --port 8000
```

The initial local launch may ask to create configuration. Open `http://localhost:8000` and configure a provider. For a server deployment, see [Docker](docker.md).

## Model providers

A minimal OpenAI-compatible configuration is included in [examples/config.json](examples/config.json):

```json
{
  "agents": {
    "defaults": {
      "provider": "gateway",
      "model": "your-model"
    }
  },
  "providers": {
    "gateway": {
      "apiBase": "https://api.example.com/v1",
      "apiKey": "${CIRNO_API_KEY}"
    }
  }
}
```

Replace the endpoint and model with values accepted by your provider. Set referenced environment variables before starting Cirno; missing references and invalid configuration produce errors. Configuration accepts camelCase and snake_case keys. Provider credentials, named model presets and connection settings can be managed in the browser. Saved connection settings take precedence over provider-constructor environment defaults.

Settings → System exposes request timeout, stream idle timeout and retry count. The configured defaults are 120 seconds for both timeouts and three retries. Proxy settings determine whether a provider uses the configured shared proxy. Restart the gateway to apply service-level settings when requested by the interface.

## Settings pages

- Models: provider connections, credentials, presets, context-window capacity and generation parameters.
- Memory: Dream, context budgets, compaction, optional embeddings and the memory library.
- Personality: Home personality, preferences, agent instructions and heartbeat instructions.
- Capabilities: access to Nodes, MCP, Skills and tool configuration.
- Channels: Telegram and Web transport configuration.
- System and Advanced: service settings, execution limits, notifications and other runtime controls.

See [Home and workspaces](home-and-workspaces.md) for file ownership and [memory](architecture/memory.md) for retrieval and maintenance behavior.

## Channels and remote browsers

Only Telegram and Web (WebSocket) channels are bundled. Enable and configure them under Settings → Channels.

For Telegram, supply a bot token and the allowed user IDs. Connection errors appear in channel status. For Web, configure the listening address, port, authentication, optional public WebSocket address and TLS certificate paths. A remote browser uses the existing gateway and needs no Cirno client installation.

Authenticated remote sessions can select Full Access. It applies to files and commands on the gateway host. Stop a running conversation before changing its access mode. Use authentication and the deployment's TLS or reverse-proxy configuration when exposing a gateway outside the local machine.

## Idle context compaction

Settings → Memory configures inactivity and two percentages of the active model's context window. Defaults are 15 minutes of inactivity, a 20% trigger and 5% recent-context retention. Idle compaction requires both inactivity and the usage trigger. A zero timeout or trigger disables it. Model preset advanced options can override either percentage; an empty value inherits the global value. Set each model's context-window capacity correctly for meaningful percentages.

Retention must be below a nonzero trigger. Compaction summarizes older context while retaining complete recent turns and paired tool calls/results within its budget. Counts are estimates until a subsequent provider request reports actual usage. Context-window pressure during execution is a separate compaction trigger.

## Projects and conversations

Create projects from the sidebar. A project has an independent ID, name, optional description and optional default working directory; two projects may use the same directory. Conversation menus move conversations into or out of projects. Project menus create conversations, rename projects or delete them. Deleting a project detaches its conversations while preserving history and working files.

The `@handle` beside a conversation is its stable address for coordination tools, not another user. Cirno is the dedicated coordination conversation; ordinary conversations retain execution tools and streamed replies. Both can create delegated conversations, send coordination messages and inspect other conversations through their tools. Only Cirno receives `user.message` for visible reply delivery. See [Goals and coordination](goals-and-dream.md).

## Nodes

Settings → Nodes manages SSH connections, host fingerprints, direct commands and persistent jobs. Supply host, port, SSH username, remote working directory and either key or password authentication. A key path refers to a file on the gateway. A blank password while editing preserves the saved password. Credentials are stored in the private Home instance database and omitted from connection listings. Saved host keys or the gateway's `known_hosts` verify the server; compare scanned fingerprints before saving them.

Execute command runs a command and returns output without creating a job. The `nodes` tool namespace also lists connections, transfers files and starts, inspects or stops persistent jobs. Job output, PID and exit status stay on the remote host; tracking records stay in Home. No remote Cirno daemon or client is installed. Persistent jobs require a POSIX shell, OpenSSH and `setsid`. An uncertain submission exposes its job ID for inspection before resubmitting.

## Service lifecycle

Settings retains Restart. There is no in-app upgrade platform or terminal configuration wizard. The CLI Apps catalog remains available for installing command-line integrations. Source installations upgrade by updating the checkout, rebuilding the browser assets and reinstalling the package; container installations rebuild or pull a published image.
