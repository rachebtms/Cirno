from cirno_setup.recipe import Recipe

recipe = Recipe(
    "pip", ('httpx',), imports=('httpx',),
    dependencies=(), commands=(),
    description='httpx',
)
