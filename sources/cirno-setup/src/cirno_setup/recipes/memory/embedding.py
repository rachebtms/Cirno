from cirno_setup.recipe import Recipe

recipe = Recipe("extra", ("cirno-memory:embedding",), imports=("onnxruntime", "tokenizers", "numpy"), description="Local embedding runtime")
