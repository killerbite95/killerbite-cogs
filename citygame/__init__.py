# __init__.py

from .citygame import CiudadVirtual

def setup(bot):
    bot.add_cog(CiudadVirtual(bot))
