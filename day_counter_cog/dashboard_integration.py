"""
Dashboard integration for DayCounter.
Per-guild page to view, create and delete day counters.
"""
import typing

from redbot.core import commands
from redbot.core.bot import Red


def dashboard_page(*args, **kwargs):
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator


class DashboardIntegration:
    bot: Red
    config: typing.Any

    async def _dashboard_denied(self, guild, kwargs, *, mod: bool = False):
        """El Dashboard solo comprueba que el usuario este en el servidor:
        cada pagina debe exigir sus propios permisos. Devuelve la respuesta
        de error o ``None`` si puede pasar."""
        user = kwargs.get("user")
        user_id = getattr(user, "id", kwargs.get("user_id"))
        if user_id is not None and user_id in self.bot.owner_ids:
            return None
        member = guild.get_member(user_id) if (guild is not None and user_id is not None) else None
        allowed = False
        if member is not None:
            perms = member.guild_permissions
            if perms.administrator or perms.manage_guild or await self.bot.is_admin(member):
                allowed = True
            elif mod and await self.bot.is_mod(member):
                allowed = True
        if allowed:
            return None
        return {
            "status": 1,
            "message": "Forbidden access.",
            "error_code": 403,
            "error_message": "No tienes permisos para acceder a esta pagina.",
        }

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    async def cog_load(self) -> None:
        dashboard_cog = self.bot.get_cog("Dashboard")
        if dashboard_cog and hasattr(dashboard_cog, "rpc"):
            try:
                dashboard_cog.rpc.third_parties_handler.add_third_party(self)
            except Exception:
                pass

    @dashboard_page(
        name="counters",
        description="Contadores de dias y cuentas atras",
        methods=("GET", "POST"),
    )
    async def rpc_counters_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Servidor no encontrado.</p></div>'}}
        denied = await self._dashboard_denied(guild, kwargs)
        if denied:
            return denied

        from .day_counter import MAX_COUNTERS, NAME_RE, _parse_date  # evita import circular

        notifications = []
        if kwargs.get("method") == "POST":
            form = kwargs.get("data", {}).get("form", {})

            def _fv(key, default=""):
                value = form.get(key, [default])
                return (value[0] if isinstance(value, list) else str(value)).strip()

            action = _fv("action")
            name = _fv("name").lower()
            if action == "save":
                date = _parse_date(_fv("date"))
                if not NAME_RE.match(name or ""):
                    notifications.append({"message": "Nombre no valido (una palabra, max. 32 caracteres).", "category": "danger"})
                elif date is None:
                    notifications.append({"message": "Fecha no valida.", "category": "danger"})
                else:
                    async with self.config.guild(guild).counters() as counters:
                        if name not in counters and len(counters) >= MAX_COUNTERS:
                            notifications.append({"message": f"Maximo {MAX_COUNTERS} contadores.", "category": "danger"})
                        else:
                            counter = counters.setdefault(name, {"created_by": getattr(kwargs.get("user"), "id", None)})
                            counter["date"] = date.isoformat()
                            title = _fv("title")[:100]
                            if title:
                                counter["title"] = title
                            description = _fv("description")[:1000]
                            if description:
                                counter["description"] = description
                            else:
                                counter.pop("description", None)
                            notifications.append({"message": f"Contador {name} guardado.", "category": "success"})
                    async with self.config.guild(guild).last_milestones() as announced:
                        announced.pop(name, None)
            elif action == "delete":
                async with self.config.guild(guild).counters() as counters:
                    if counters.pop(name, None) is not None:
                        notifications.append({"message": f"Contador {name} borrado.", "category": "success"})
            elif action == "milestones":
                channel_id = _fv("milestone_channel")
                channel = guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
                await self.config.guild(guild).milestone_channel.set(channel.id if channel else None)
                notifications.append({"message": "Canal de hitos guardado.", "category": "success"})

        counters = await self.get_counters(guild)
        rows = []
        for name, data in sorted(counters.items()):
            state = self.counter_state(data)
            rows.append({
                "name": name,
                "title": data.get("title") or name,
                "description": data.get("description") or "",
                "date": state["date"].isoformat(),
                "days": state["days"],
                "future": state["future"],
            })
        milestone_channel = await self.config.guild(guild).milestone_channel()
        channels = [
            {"id": ch.id, "name": f"#{ch.name}", "selected": ch.id == milestone_channel}
            for ch in sorted(guild.text_channels, key=lambda c: c.position)
        ]

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-calendar"></i> DayCounter</h3>
  <p class="trini-tp-subtitle">Contadores de dias (fecha pasada) y cuentas atras (fecha futura).</p>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-list me-1"></i> Contadores</h4><span class="badge bg-gradient-info">{{ rows|length }}</span></div>
    {% if rows|length > 0 %}
    <div class="table-responsive">
      <table class="table trini-table trini-tp-table">
        <thead><tr><th>Nombre</th><th>Titulo</th><th>Fecha</th><th>Dias</th><th></th></tr></thead>
        <tbody>
          {% for r in rows %}
          <tr>
            <td><code>{{ r.name }}</code></td>
            <td>{{ r.title }}</td>
            <td><small>{{ r.date }}</small></td>
            <td>{% if r.future %}<span class="badge bg-gradient-warning">faltan {{ r.days }}</span>{% else %}<strong>{{ r.days }}</strong>{% endif %}</td>
            <td>
              <form method="POST" style="display:inline">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input type="hidden" name="action" value="delete">
                <input type="hidden" name="name" value="{{ r.name }}">
                <button type="submit" class="btn btn-xs bg-gradient-danger mb-0" onclick="return confirm('¿Borrar este contador?')"><i class="fa fa-trash"></i></button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="trini-tp-empty"><i class="fa fa-calendar fa-3x"></i><p>No hay contadores.</p></div>
    {% endif %}
  </div>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-plus me-1"></i> Crear o editar</h4></div>
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="action" value="save">
      <div class="row align-items-end">
        <div class="col-lg-2 col-md-4 mb-3"><label class="form-label text-xs mb-1">Nombre</label>
          <input type="text" class="form-control form-control-sm" name="name" maxlength="32" placeholder="principal" required></div>
        <div class="col-lg-2 col-md-4 mb-3"><label class="form-label text-xs mb-1">Fecha</label>
          <input type="date" class="form-control form-control-sm" name="date" required></div>
        <div class="col-lg-3 col-md-4 mb-3"><label class="form-label text-xs mb-1">Titulo</label>
          <input type="text" class="form-control form-control-sm" name="title" maxlength="100"></div>
        <div class="col-lg-3 col-md-8 mb-3"><label class="form-label text-xs mb-1">Descripcion</label>
          <input type="text" class="form-control form-control-sm" name="description" maxlength="1000"></div>
        <div class="col-lg-2 col-md-4 mb-3"><button type="submit" class="btn btn-xs bg-gradient-success mb-0 w-100"><i class="fa fa-save me-1"></i> Guardar</button></div>
      </div>
    </form>
  </div>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-trophy me-1"></i> Anuncio de hitos</h4></div>
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="action" value="milestones">
      <div class="row align-items-end">
        <div class="col-lg-4 col-md-8 mb-3"><label class="form-label text-xs mb-1">Canal</label>
          <select class="form-select form-select-sm" name="milestone_channel">
            <option value="">-- Desactivado --</option>
            {% for ch in channels %}<option value="{{ ch.id }}" {{ "selected" if ch.selected }}>{{ ch.name }}</option>{% endfor %}
          </select></div>
        <div class="col-lg-2 col-md-4 mb-3"><button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100"><i class="fa fa-save me-1"></i> Guardar</button></div>
      </div>
    </form>
  </div>
</div>
"""
        result = {"status": 0, "web_content": {"source": source, "rows": rows, "channels": channels}}
        if notifications:
            result["notifications"] = notifications
        return result
