from cirno_setup.context import Context
from cirno_setup.recipe import Recipe


class YtdlpRecipe(Recipe):
    def install(self, context: Context) -> None:
        super().install(context)
        # Use the tool's ordinary user configuration instead of wrapping and
        # rewriting every invocation. Existing user options take precedence.
        configuration = context.home / ".config/yt-dlp/config"
        configuration.parent.mkdir(parents=True, exist_ok=True)
        if not configuration.exists():
            configuration.write_text("--js-runtimes node\n", encoding="utf-8")


recipe = YtdlpRecipe("pip", ('yt-dlp[default]==2026.10.26',), dependencies=('tools.node',), imports=('yt_dlp',), commands=('yt-dlp',), description='yt-dlp[default]')
