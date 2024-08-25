from .simplesuggestions import SimpleSuggestions

def setup(bot):
    bot.add_cog(SimpleSuggestions(bot))
