from cirno_setup.recipe import Recipe

recipe = Recipe(
    "pip", ('CairoSVG',), imports=('cairosvg',),
    dependencies=('system.cairo',), commands=('cairosvg',),
    description='CairoSVG',
)
