# __init__.py

from .advancedcaptcha import AdvancedCaptcha

def setup(bot):
    bot.add_cog(AdvancedCaptcha(bot))
