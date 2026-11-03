# Backup and restore

Available in Cirno 0.1.5, in both image variants.

Open **Settings → Backup & restore**. Export produces a downloadable `.tar.gz` archive. Both upload and download use the existing Web UI port and stream files through disk; no additional port or large in-memory archive is required. Finish or stop active operations first. Export refuses a busy runtime rather than cancelling tasks.

## What is included

The entire instance directory is included: configuration and provider credentials, account and browser sessions, MCP and Tools settings, all memory databases and evidence, personality files, conversations, display history, saved model context, Goals, pending actions, Skills and their history, inbox data, CLI configuration and persistent user packages. Each SQLite database is copied with SQLite's backup API, including committed WAL contents.

Temporary export archives, staged imports, process locks and SQLite WAL/SHM sidecars are excluded. They are not independent user data. Running processes, open SSH connections and live terminal processes cannot be serialized; saved conversation recovery state remains available after restart. Bundled binaries and embedding weights are supplied by the image. A backup of persistent packages requires a compatible operating system, Python version and CPU architecture.

## Extra files and folders

The instance is always included. The page also discovers existing current and historical workspaces, project directories, and common CLI data locations. These include GitHub/Gitea login configuration, SSH, Git credentials, XDG configuration/data, Python packages and tool environments, npm, uv, pipx, Go, Bun, nvm, Hugging Face data and Homebrew when present. Discovery checks paths, not credential contents. Locations already inside the instance are marked as automatically included. Image-owned service dependencies are not extra user data.

Select additional files or directories, or enter an absolute path. The default workspace and Agent Home are selected initially if they are outside the instance. Other external paths are opt-in. Previous selections are saved for the next export. Nested selections are deduplicated. Backups contain credentials and API keys without encryption; store the archive privately.

Host environment variables and Compose files outside the instance are not captured automatically. Select those files separately and preserve the deployment mounts when upgrading.

External workspaces, custom embedding weights, manually placed scripts and tools outside the instance must be selected if they should be included. Files installed only into the image's writable layer are not automatically persistent just because a backup feature exists. Put permanent changes to bundled tools in a derived image, or explicitly include the relevant directories.

## Importing a backup

Import first uploads, validates and stages the archive. The preview shows its version, date, original instance location and extra paths. Extra destinations may be edited; leave a destination blank to skip it. Confirm **Restore and restart** to schedule the replacement, then restart the service through the existing control.

Restoration runs before the service opens its configuration, databases or runtime consumers. The current instance contents are replaced, preserving the restore workspace until completion. External directories are merged: matching files are overwritten, while unrelated files remain. A failed instance copy restores the prior instance; an interrupted attempt is recovered on the next startup. An error restoring an external destination prevents the instance replacement and service startup; external files copied before the error may already have changed.

Use the restored account to sign in afterward. Restored pending approvals and questions retain their saved state. Restore to the same instance/workspace locations for exact path fidelity. When moving between hosts, review external destinations, absolute tool paths and provider/server settings before resuming work. Files that agents changed outside the selected backup paths are not reverted.
