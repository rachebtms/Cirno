"""Use Playwright's unmodified driver and default Chromium installation."""

from pathlib import Path

from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def executable(context: Context) -> str | None:
    result = context.inspect([str(context.python), "-c", "from playwright.sync_api import sync_playwright; "
        "p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()"])
    return result.stdout.strip() if result.returncode == 0 else None


def verify(context: Context, recipe: Recipe) -> Verification:
    # Default headless launch also checks the default Headless Shell, rather
    # than requiring clients to use a Cirno-specific channel override.
    launch_timeout_ms = (context.policy.subprocess_timeout(maximum=30) or 0) * 1000
    result = context.inspect([str(context.python), "-c", "from playwright.sync_api import sync_playwright; "
        f"p=sync_playwright().start(); b=p.chromium.launch(headless=True, timeout={launch_timeout_ms}); b.close(); p.stop()"])
    path = executable(context)
    link = context.root / "bin/chromium"
    valid = result.returncode == 0 and path is not None and link.is_symlink() and link.resolve() == Path(path).resolve()
    return Verification(valid, result.stderr.strip()[-1000:])


def install(context: Context, recipe: Recipe) -> None:
    context.run([str(context.python), "-m", "playwright", "install", "chromium"])
    path = executable(context)
    if path is None or not Path(path).is_file():
        raise RuntimeError("Playwright Chromium installation did not produce an executable")
    link = context.root / "bin/chromium"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.unlink(missing_ok=True)
    link.symlink_to(path)
