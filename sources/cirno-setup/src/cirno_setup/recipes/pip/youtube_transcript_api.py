from cirno_setup.recipe import Recipe

recipe = Recipe(
    "pip", ('youtube-transcript-api',), imports=('youtube_transcript_api',),
    dependencies=(), commands=('youtube_transcript_api',),
    description='youtube-transcript-api',
)
