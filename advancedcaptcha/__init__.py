from .advancedcaptcha import AdvancedCaptcha

async def setup(bot):
    await bot.add_cog(AdvancedCaptcha(bot))
