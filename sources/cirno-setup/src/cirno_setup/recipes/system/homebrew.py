from cirno_setup.recipe import Recipe

recipe = Recipe("apt", ('build-essential', 'file', 'procps', 'locales', 'patch', 'bzip2', 'xz-utils', 'unzip'), description='homebrew')
