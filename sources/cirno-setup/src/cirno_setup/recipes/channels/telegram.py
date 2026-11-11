from cirno_setup.contracts.telegram import REQUIREMENTS
from cirno_setup.recipe import Recipe

recipe = Recipe("pip", REQUIREMENTS, imports=("telegram", "socksio"), target="service", description="Telegram channel dependencies")
