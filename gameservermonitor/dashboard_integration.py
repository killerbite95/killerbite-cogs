import typing
from redbot.core import commands
from redbot.core.bot import Red

def dashboard_page(*args, **kwargs):
    """
    Decorador para marcar métodos como páginas del dashboard.
    Al aplicarlo se guardan los parámetros en __dashboard_decorator_params__
    """
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator

class DashboardIntegration:
    bot: Red

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        """
        Listener que se dispara cuando el Dashboard se carga.
        Se registra este cog como un tercer party en el dashboard.
        """
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)
