"""
Dashboard Integration para GameServerMonitor.
Proporciona integración con Red-Dashboard.
By Killerbite95
"""

import typing
from typing import Callable, Any, Tuple, Dict
import logging

from redbot.core import commands
from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.gameservermonitor.dashboard")


def dashboard_page(
    name: str = None,
    description: str = None,
    methods: Tuple[str, ...] = ("GET",),
    is_owner: bool = False,
    **kwargs
) -> Callable:
    """
    Decorador para marcar métodos como páginas del dashboard.
    
    Args:
        name: Nombre de la página (usado en la URL)
        description: Descripción de la página
        methods: Métodos HTTP permitidos (GET, POST, etc.)
        is_owner: Si True, solo el owner del bot puede acceder
        **kwargs: Argumentos adicionales para el dashboard
        
    Returns:
        Decorador que marca el método como página del dashboard
        
    Example:
        @dashboard_page(name="servers", description="Lista de servidores")
        async def rpc_servers(self, guild_id: int, **kwargs):
            ...
    """
    def decorator(func: Callable) -> Callable:
        func.__dashboard_decorator_params__ = (
            (name,),
            {
                "description": description,
                "methods": methods,
                "is_owner": is_owner,
                **kwargs
            }
        )
        return func
    return decorator


class DashboardIntegration:
    """
    Clase base para integración con Red-Dashboard.
    
    Los cogs que heredan de esta clase pueden usar el decorador @dashboard_page
    para crear páginas en el panel web del dashboard.
    
    Attributes:
        bot: Instancia del bot de Red
    """
    
    bot: Red

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        """
        Listener que se dispara cuando el Dashboard se carga.
        Registra este cog como third party en el dashboard.
        
        Args:
            dashboard_cog: La instancia del cog Dashboard
        """
        try:
            if hasattr(dashboard_cog, 'rpc') and hasattr(dashboard_cog.rpc, 'third_parties_handler'):
                dashboard_cog.rpc.third_parties_handler.add_third_party(self)
                logger.info("GameServerMonitor registrado en el Dashboard correctamente.")
            else:
                logger.warning("Dashboard cog no tiene la estructura esperada para third parties.")
        except Exception as e:
            logger.error(f"Error al registrar en el Dashboard: {e!r}")
    
    @staticmethod
    def create_html_table(
        headers: typing.List[str],
        rows: typing.List[typing.List[str]],
        table_class: str = "table table-bordered table-striped table-hover"
    ) -> str:
        """
        Crea una tabla HTML con Bootstrap.
        
        Args:
            headers: Lista de encabezados
            rows: Lista de filas (cada fila es una lista de celdas)
            table_class: Clases CSS para la tabla
            
        Returns:
            String HTML de la tabla
        """
        html = f'<table class="{table_class}">\n<thead class="table-dark">\n<tr>\n'
        
        for header in headers:
            html += f'<th scope="col">{header}</th>\n'
        
        html += '</tr>\n</thead>\n<tbody>\n'
        
        for row in rows:
            html += '<tr>\n'
            for cell in row:
                html += f'<td>{cell}</td>\n'
            html += '</tr>\n'
        
        html += '</tbody>\n</table>'
        return html
    
    @staticmethod
    def create_notification(
        message: str,
        category: str = "info"
    ) -> Dict[str, Any]:
        """
        Crea una notificación para el dashboard.
        
        Args:
            message: Mensaje a mostrar
            category: Categoría (info, success, warning, error)
            
        Returns:
            Dict con la estructura de notificación
        """
        return {"message": message, "category": category}
    
    @staticmethod
    def success_response(
        notifications: typing.List[Dict[str, str]] = None,
        redirect_url: str = None,
        web_content: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Crea una respuesta de éxito para el dashboard.
        
        Args:
            notifications: Lista de notificaciones a mostrar
            redirect_url: URL a la que redirigir
            web_content: Contenido web a mostrar
            
        Returns:
            Dict con la respuesta formateada
        """
        response = {"status": 0}
        if notifications:
            response["notifications"] = notifications
        if redirect_url:
            response["redirect_url"] = redirect_url
        if web_content:
            response["web_content"] = web_content
        return response
    
    @staticmethod
    def error_response(error_message: str) -> Dict[str, Any]:
        """
        Crea una respuesta de error para el dashboard.
        
        Args:
            error_message: Mensaje de error
            
        Returns:
            Dict con la respuesta de error
        """
        return {"status": 1, "error": error_message}
