from cirno_setup.recipe import Recipe

recipe = Recipe(
    "pip", ('marker-pdf',), imports=('marker', 'torch'),
    dependencies=('apt.libgomp1',), commands=('marker', 'marker_single'),
    description='marker-pdf',
)
