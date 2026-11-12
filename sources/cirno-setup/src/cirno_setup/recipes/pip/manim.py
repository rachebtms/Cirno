from cirno_setup.recipe import Recipe

recipe = Recipe(
    "pip", ('manim',), imports=('manim',),
    dependencies=('system.cairo', 'system.ffmpeg', 'system.fonts', 'system.latex', 'apt.dvisvgm', 'apt.tipa'), commands=('manim',),
    description='manim',
)
