# __init__.py

import logging  # Importar el módulo logging
log = logging.getLogger("red.citygame")  # Configurar el logger

from .citygame import CiudadVirtual

async def setup(bot):
    await bot.add_cog(CiudadVirtual(bot))
    log.info("Cog 'CiudadVirtual' cargado exitosamente.")
