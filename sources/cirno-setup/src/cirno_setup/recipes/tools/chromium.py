from cirno_setup.recipe import Recipe

recipe = Recipe("browser", dependencies=("pip.playwright", "system.browser", "system.fonts"), description="Chromium and Playwright")
