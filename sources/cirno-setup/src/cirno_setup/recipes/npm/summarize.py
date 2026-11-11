from cirno_setup.recipe import Recipe

recipe = Recipe("npm", ('@steipete/summarize@0.26.0',), ("tools.node",), commands=('summarize',), description='summarize')
