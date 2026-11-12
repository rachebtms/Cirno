from cirno_setup.recipe import Recipe

recipe = Recipe(
    "pip", ('beautifulsoup4',), imports=('bs4',),
    dependencies=(), commands=(),
    description='beautifulsoup4',
)
