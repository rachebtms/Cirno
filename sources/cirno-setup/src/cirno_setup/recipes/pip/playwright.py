from cirno_setup.recipe import Recipe

recipe = Recipe("pip", ('playwright==1.65.0',), dependencies=("system.node_runtime",), imports=('playwright',), commands=('playwright',), description='playwright')
