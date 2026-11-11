from pathlib import Path

from cirno_setup.recipe import Recipe

packages = tuple((Path(__file__).parents[2] / "assets/browser-system.txt").read_text().split())
recipe = Recipe("apt", packages, description="Chromium system libraries")
