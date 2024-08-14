from .roomer_ui import RoomerUI

async def setup(bot):
    await bot.add_cog(RoomerUI(bot))
