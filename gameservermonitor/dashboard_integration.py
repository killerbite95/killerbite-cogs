import typing
from redbot.core import commands

# Decorador para definir páginas en el dashboard
def dashboard_page(*args, **kwargs):
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator

class DashboardIntegration:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    @dashboard_page(name="servers")
    async def rpc_callback_servers(self, **kwargs) -> typing.Dict[str, typing.Any]:
        """
        Callback para el dashboard que muestra una tabla HTML con los servidores monitoreados.
        Se espera que se pase 'guild_id' en los kwargs para identificar el servidor.
        """
        guild_id = kwargs.get("guild_id")
        if guild_id is None:
            return {"status": 1, "error": "guild_id no especificado."}
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            return {"status": 1, "error": "Servidor no encontrado."}

        servers = await self.config.guild(guild).servers()
        html_content = "<h1>Game Server Monitor</h1>"
        html_content += (
            "<table border='1' style='border-collapse: collapse;'>"
            "<tr><th>Server IP</th><th>Game</th><th>Channel ID</th><th>Domain</th></tr>"
        )
        for server_ip, data in servers.items():
            game = data.get("game", "N/A")
            channel_id = data.get("channel_id", "N/A")
            domain = data.get("domain", "N/A")
            html_content += (
                f"<tr><td>{server_ip}</td><td>{game.upper()}</td>"
                f"<td>{channel_id}</td><td>{domain if domain else 'N/A'}</td></tr>"
            )
        html_content += "</table>"
        return {
            "status": 0,
            "web_content": {
                "source": html_content
            }
        }
