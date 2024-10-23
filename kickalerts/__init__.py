from .simplesuggestions import SimpleSuggestions

async def setup(bot):
    await bot.add_cog(SimpleSuggestions(bot))
