"""Generado automaticamente. No se importa: solo sirve para que ``redgettext``
extraiga al catalogo los textos que no detecta por si solo (constantes marcadas
con N_(), docstrings de comandos hibridos y textos dentro de decoradores).
"""
from redbot.core.i18n import Translator

_ = Translator("GameServerMonitor", __file__)


def _strings() -> None:
    _("\n        Shows detailed server statistics.\n        \n        You can use the real IP, public IP, or server_id.\n        \n        **Example:** `[p]serverstats 192.168.1.1:27015`\n        ")
    _("\n        Shows the player history of a server with an ASCII graph.\n        \n        **Examples:**\n        `[p]gsmhistory 192.168.1.1:27015` - Last 24 hours\n        `[p]gsmhistory 192.168.1.1:27015 12` - Last 12 hours\n        ")
    _("\n        Shows the list of players connected to a server.\n        \n        Displays name, score and connection time.\n        \n        **Example:** `[p]gsmplayers 192.168.1.1:27015`\n        ")
    _("\n        Shows the current map of a server.\n        \n        For Minecraft servers, shows the version instead.\n        \n        **Example:** `[p]gsmmap 192.168.1.1:27015`\n        ")
