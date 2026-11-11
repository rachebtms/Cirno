# Loaded by login shells and by the agent's non-interactive Bash.
# Login shells reset PATH, so restore image tools before selecting an nvm version.
export PATH="$HOME/.cirno/state/tools/python/bin:$HOME/.cirno/state/tools/bin:$HOME/.cirno/state/tools/npm/bin:$HOME/.cirno/state/tools/bun/bin:$HOME/.cirno/state/tools/bundled/pandoc/bin:$HOME/.cirno/state/tools/bundled/xurl/bin:/app/.venv/bin:/opt/cirno/bin:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:$PATH"
export NVM_DIR="${NVM_DIR:-$HOME/.cirno/state/tools/nvm}"
export VIRTUAL_ENV="${VIRTUAL_ENV:-$HOME/.cirno/state/tools/python}"
mkdir -p "$NVM_DIR"
if [ -f "$NVM_DIR/nvm.sh" ]; then
    . "$NVM_DIR/nvm.sh"
fi
