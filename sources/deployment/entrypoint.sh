#!/bin/sh
dir="$HOME/.cirno"

# Drop privileges when the container starts as root. Chown the data dir so the non-root user can write it, then
# re-exec as cirno. Fail closed: if the privilege drop cannot be performed,
# exit rather than run the agent as root.
if [ "$(id -u)" = "0" ]; then
    chown -R cirno:cirno "$dir" 2>/dev/null || echo "[entrypoint] warning: chown $dir failed"
    if setpriv --reuid=cirno --regid=cirno --init-groups true 2>/dev/null; then
        echo "[entrypoint] dropping privileges to cirno via setpriv"
        exec setpriv --reuid=cirno --regid=cirno --init-groups "$0" "$@"
    fi
    echo "[entrypoint] error: started as root but setpriv privilege drop failed — refusing to run as root" >&2
    exit 1
fi

# Already non-root: make sure the data dir is writable before starting.
if [ -d "$dir" ] && [ ! -w "$dir" ]; then
    owner_uid=$(stat -c %u "$dir" 2>/dev/null || stat -f %u "$dir" 2>/dev/null)
    cat >&2 <<EOF
Error: $dir is not writable (owned by UID $owner_uid, running as UID $(id -u)).

Fix (pick one):
  Host:   sudo chown -R 1000:1000 ~/.cirno
  Docker: docker run --user \$(id -u):\$(id -g) ...
  Podman: podman run --userns=keep-id ...
EOF
    exit 1
fi

if [ "${CIRNO_FULL_IMAGE:-}" = "1" ]; then
    mkdir -p "$dir/state/cli/config" "$dir/state/cli/data" "$dir/state/cli/cache" \
        "$dir/state/tools/bin" "$dir/state/tools/npm" "$dir/state/tools/nvm"
    if [ -f "$CIRNO_SHELL_VENV/pyvenv.cfg" ]; then
        /app/.venv/bin/python -m venv --upgrade "$CIRNO_SHELL_VENV" || exit 1
    else
        /app/.venv/bin/python -m venv "$CIRNO_SHELL_VENV" || exit 1
    fi
    if [ ! -e "$HOME/.config" ] && [ ! -L "$HOME/.config" ]; then
        ln -s "$dir/state/cli/config" "$HOME/.config"
    fi
    for tool in xurl ssh summarize mcporter; do
        mkdir -p "$dir/state/cli/$tool"
        chmod 700 "$dir/state/cli/$tool"
        if [ ! -e "$HOME/.$tool" ] && [ ! -L "$HOME/.$tool" ]; then
            ln -s "$dir/state/cli/$tool" "$HOME/.$tool"
        fi
    done
fi

if [ "$CIRNO_DOCKER_BOOTSTRAP" = "1" ]; then
    # Explicit config selectors belong to the CLI; bootstrap only the default instance.
    initialize_default=1
    for argument in "$@"; do
        case "$argument" in
            --config|--config=*|-c*) initialize_default=0; break ;;
        esac
    done
    if [ "$initialize_default" = "1" ]; then
        config="$dir/config.json"
        /app/.venv/bin/python -m cirno_server.cli.docker_bootstrap "$config" || exit 1
        set -- "$@" --config "$config"
    fi
fi

exec /app/.venv/bin/cirno "$@"
