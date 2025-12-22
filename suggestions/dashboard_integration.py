"""
Dashboard integration for SimpleSuggestions.
Provides web interface for managing suggestions.
"""
import typing
import discord
from redbot.core import commands
from redbot.core.bot import Red

from .storage import SuggestionStatus, STATUS_CONFIG


def dashboard_page(*args, **kwargs):
    """
    Decorador para marcar métodos como páginas del dashboard.
    Al aplicarlo, se almacenan los parámetros en __dashboard_decorator_params__.
    """
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator


class DashboardIntegration:
    bot: Red
    config: typing.Any
    storage: typing.Any

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        """
        Listener que se dispara cuando se carga el Dashboard.
        Se registra este cog como tercer party.
        """
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)
    
    @dashboard_page(name="suggestions", description="Ver y gestionar sugerencias", methods=("GET", "POST"))
    async def rpc_suggestions_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """
        Página principal del dashboard para ver sugerencias.
        Soporta filtrado por estado, autor y búsqueda.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        
        # Get query parameters
        request = kwargs.get("request")
        page = int(kwargs.get("page", 1))
        per_page = 20
        status_filter = kwargs.get("status", "all")
        search = kwargs.get("search", "")
        
        # Get suggestions
        filter_status = None
        if status_filter and status_filter != "all":
            try:
                filter_status = SuggestionStatus(status_filter)
            except ValueError:
                pass
        
        all_suggestions = await self.storage.get_all_suggestions(guild, status_filter=filter_status)
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            all_suggestions = [
                s for s in all_suggestions 
                if search_lower in s.content.lower() or search_lower in str(s.suggestion_id)
            ]
        
        # Pagination
        total = len(all_suggestions)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        suggestions = all_suggestions[start:start + per_page]
        
        # Build HTML
        html_content = """
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; }
            .status-pending { background: #3498db; color: white; }
            .status-approved { background: #2ecc71; color: white; }
            .status-denied { background: #e74c3c; color: white; }
            .status-in_review { background: #f39c12; color: white; }
            .status-planned { background: #9b59b6; color: white; }
            .status-in_progress { background: #e67e22; color: white; }
            .status-implemented { background: #27ae60; color: white; }
            .status-duplicate { background: #95a5a6; color: white; }
            .status-wont_do { background: #7f8c8d; color: white; }
            .vote-up { color: #2ecc71; }
            .vote-down { color: #e74c3c; }
        </style>
        <div class="container-fluid mt-4">
            <h2 class="mb-4">📋 Sugerencias</h2>
            
            <!-- Filters -->
            <div class="row mb-4">
                <div class="col-md-4">
                    <select class="form-select" id="statusFilter" onchange="filterSuggestions()">
                        <option value="all">Todos los estados</option>
        """
        
        for status in SuggestionStatus:
            info = STATUS_CONFIG.get(status, {})
            selected = "selected" if status_filter == status.value else ""
            html_content += f'<option value="{status.value}" {selected}>{info.get("emoji", "")} {info.get("label", status.value)}</option>'
        
        html_content += f"""
                    </select>
                </div>
                <div class="col-md-4">
                    <input type="text" class="form-control" id="searchInput" placeholder="Buscar..." value="{search}">
                </div>
                <div class="col-md-4">
                    <button class="btn btn-primary" onclick="filterSuggestions()">🔍 Buscar</button>
                </div>
            </div>
            
            <!-- Stats -->
            <div class="row mb-4">
                <div class="col">
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title">📊 Estadísticas</h5>
                            <p class="card-text">Total: <strong>{total}</strong> sugerencias</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Table -->
            <table class="table table-hover">
                <thead class="table-dark">
                    <tr>
                        <th>#</th>
                        <th>Contenido</th>
                        <th>Autor</th>
                        <th>Votos</th>
                        <th>Estado</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for s in suggestions:
            author = self.bot.get_user(s.author_id)
            author_name = author.display_name if author else f"ID: {s.author_id}"
            status_info = STATUS_CONFIG.get(s.status, {})
            status_class = f"status-{s.status.value}"
            content_preview = s.content[:100] + ("..." if len(s.content) > 100 else "")
            
            html_content += f"""
                <tr>
                    <td><strong>#{s.suggestion_id}</strong></td>
                    <td>{content_preview}</td>
                    <td>{author_name}</td>
                    <td>
                        <span class="vote-up">👍 {s.upvotes}</span> | 
                        <span class="vote-down">👎 {s.downvotes}</span>
                    </td>
                    <td><span class="status-badge {status_class}">{status_info.get("emoji", "")} {status_info.get("label", s.status.value)}</span></td>
                    <td>
                        <a href="?page_name=manage_suggestion&suggestion_id={s.suggestion_id}" class="btn btn-sm btn-primary">Gestionar</a>
                    </td>
                </tr>
            """
        
        # Pagination
        html_content += """
                </tbody>
            </table>
            
            <!-- Pagination -->
            <nav>
                <ul class="pagination justify-content-center">
        """
        
        for p in range(1, total_pages + 1):
            active = "active" if p == page else ""
            html_content += f'<li class="page-item {active}"><a class="page-link" href="?page={p}&status={status_filter}&search={search}">{p}</a></li>'
        
        html_content += """
                </ul>
            </nav>
        </div>
        
        <script>
        function filterSuggestions() {
            const status = document.getElementById('statusFilter').value;
            const search = document.getElementById('searchInput').value;
            window.location.href = `?status=${status}&search=${encodeURIComponent(search)}`;
        }
        </script>
        """
        
        return {"status": 0, "web_content": {"source": html_content}}
    
    @dashboard_page(name="manage_suggestion", description="Gestionar una sugerencia", methods=("GET", "POST"))
    async def rpc_manage_suggestion(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """
        Página para gestionar una sugerencia individual.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        
        suggestion_id = int(kwargs.get("suggestion_id", 0))
        if not suggestion_id:
            return {"status": 1, "error": "ID de sugerencia no proporcionado."}
        
        suggestion = await self.storage.get_suggestion(guild, suggestion_id)
        if not suggestion:
            return {"status": 1, "error": "Sugerencia no encontrada."}
        
        # Handle form submission
        if kwargs.get("method") == "POST":
            new_status = kwargs.get("new_status")
            reason = kwargs.get("reason", "")
            
            if new_status:
                try:
                    status_enum = SuggestionStatus(new_status)
                    user = kwargs.get("user")
                    user_id = user.id if user else 0
                    
                    old_status = suggestion.status
                    await self.storage.update_status(guild, suggestion_id, status_enum, user_id, reason or None)
                    
                    return {
                        "status": 0,
                        "notifications": [{"message": f"Estado actualizado a {status_enum.value}", "category": "success"}],
                        "redirect_url": kwargs.get("request_url")
                    }
                except ValueError:
                    return {"status": 1, "error": "Estado inválido."}
        
        # Build page
        author = self.bot.get_user(suggestion.author_id)
        author_name = author.display_name if author else f"ID: {suggestion.author_id}"
        status_info = STATUS_CONFIG.get(suggestion.status, {})
        
        html_content = f"""
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <div class="container mt-4">
            <a href="?page_name=suggestions" class="btn btn-secondary mb-3">← Volver</a>
            
            <div class="card">
                <div class="card-header">
                    <h4>Sugerencia #{suggestion.suggestion_id}</h4>
                </div>
                <div class="card-body">
                    <p><strong>Autor:</strong> {author_name}</p>
                    <p><strong>Estado:</strong> {status_info.get("emoji", "")} {status_info.get("label", suggestion.status.value)}</p>
                    <p><strong>Votos:</strong> 👍 {suggestion.upvotes} | 👎 {suggestion.downvotes}</p>
                    <hr>
                    <p><strong>Contenido:</strong></p>
                    <div class="bg-light p-3 rounded">{suggestion.content}</div>
                    {f'<p class="mt-3"><strong>Motivo anterior:</strong> {suggestion.reason}</p>' if suggestion.reason else ''}
                </div>
            </div>
            
            <div class="card mt-4">
                <div class="card-header">
                    <h5>Cambiar Estado</h5>
                </div>
                <div class="card-body">
                    <form method="POST">
                        <div class="mb-3">
                            <label class="form-label">Nuevo Estado</label>
                            <select name="new_status" class="form-select" required>
        """
        
        for status in SuggestionStatus:
            info = STATUS_CONFIG.get(status, {})
            selected = "selected" if status == suggestion.status else ""
            html_content += f'<option value="{status.value}" {selected}>{info.get("emoji", "")} {info.get("label", status.value)}</option>'
        
        html_content += """
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Motivo (opcional)</label>
                            <textarea name="reason" class="form-control" rows="3"></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary">Actualizar</button>
                    </form>
                </div>
            </div>
            
            <!-- History -->
            <div class="card mt-4">
                <div class="card-header">
                    <h5>📜 Historial de Cambios</h5>
                </div>
                <div class="card-body">
        """
        
        if suggestion.history:
            html_content += '<ul class="list-group">'
            for entry in reversed(suggestion.history[-10:]):
                changer = self.bot.get_user(entry.get("changed_by", 0))
                changer_name = changer.display_name if changer else "Desconocido"
                html_content += f"""
                    <li class="list-group-item">
                        <strong>{entry.get("old_status")} → {entry.get("new_status")}</strong>
                        por {changer_name}
                        {f'<br><small class="text-muted">{entry.get("reason")}</small>' if entry.get("reason") else ''}
                    </li>
                """
            html_content += '</ul>'
        else:
            html_content += '<p class="text-muted">No hay cambios registrados.</p>'
        
        html_content += """
                </div>
            </div>
        </div>
        """
        
        return {"status": 0, "web_content": {"source": html_content}}

