from cirno_setup.recipe import Recipe

# Reuse the compiler, pkg-config, Cairo and Pango headers already shared by
# research tools; FFI and Python headers also support source wheels on ARM64.
recipe = Recipe(
    "apt", ("python3-dev", "libffi-dev"), dependencies=("system.development",),
    description="Cairo rendering and Python extension build dependencies",
)
