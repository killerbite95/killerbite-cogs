"""
Dashboard integration for AutoNick.
Provides web interface for managing nickname settings and forbidden words.
"""
import typing
import html as html_mod
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

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    @dashboard_page(
        name="settings",
        description="Configuración de AutoNick",
        methods=("GET", "POST"),
        is_owner=True,
    )
    async def rpc_autonick_page(self, **kwargs) -> typing.Dict[str, typing.Any]:
        method = kwargs.get("method", "GET")
        notifications = []

        # POST — handle actions
        if method == "POST":
            form = kwargs.get("data", {}).get("form", {})
            action = form.get("action", [""])[0] if isinstance(form.get("action"), list) else str(form.get("action", ""))
            guild_id_str = form.get("guild_id", ["0"])[0] if isinstance(form.get("guild_id"), list) else str(form.get("guild_id", "0"))

            try:
                guild = self.bot.get_guild(int(guild_id_str))
            except (ValueError, TypeError):
                guild = None

            if action == "update_settings" and guild:
                try:
                    channel_str = form.get("channel", [""])[0] if isinstance(form.get("channel"), list) else ""
                    cooldown_str = form.get("cooldown", ["60"])[0] if isinstance(form.get("cooldown"), list) else "60"

                    if channel_str:
                        await self.config.guild(guild).channel.set(int(channel_str))
                    else:
                        await self.config.guild(guild).channel.set(None)

                    cooldown = max(0, int(cooldown_str))
                    await self.config.guild(guild).cooldown.set(cooldown)
                    notifications.append({"message": "Configuración actualizada.", "category": "success"})
                except Exception as e:
                    notifications.append({"message": f"Error: {e}", "category": "danger"})

            elif action == "add_forbidden":
                word = form.get("word", [""])[0] if isinstance(form.get("word"), list) else ""
                word = word.strip().lower()
                if word:
                    try:
                        forbidden = await self.config.forbidden_names()
                        if word not in forbidden:
                            forbidden.append(word)
                            await self.config.forbidden_names.set(forbidden)
                            notifications.append({"message": f"Palabra '{html_mod.escape(word)}' añadida.", "category": "success"})
                        else:
                            notifications.append({"message": "Esa palabra ya existe.", "category": "warning"})
                    except Exception as e:
                        notifications.append({"message": f"Error: {e}", "category": "danger"})

            elif action == "remove_forbidden":
                word = form.get("word", [""])[0] if isinstance(form.get("word"), list) else ""
                word = word.strip().lower()
                if word:
                    try:
                        forbidden = await self.config.forbidden_names()
                        if word in forbidden:
                            forbidden.remove(word)
                            await self.config.forbidden_names.set(forbidden)
                            notifications.append({"message": f"Palabra '{html_mod.escape(word)}' eliminada.", "category": "success"})
                        else:
                            notifications.append({"message": "Esa palabra no está en la lista.", "category": "warning"})
                    except Exception as e:
                        notifications.append({"message": f"Error: {e}", "category": "danger"})

        # GET — collect data
        try:
            all_guilds = await self.config.all_guilds()
            forbidden_names = await self.config.forbidden_names()
        except Exception:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Error al cargar datos.</p></div>'}}

        guilds_data = []
        for gid, data in all_guilds.items():
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            channel_id = data.get("channel")
            cooldown = data.get("cooldown", 60)

            channel_name = ""
            if channel_id:
                ch = guild.get_channel(channel_id)
                channel_name = f"#{ch.name}" if ch else f"ID: {channel_id}"

            # Build channel options
            text_channels = []
            for ch in sorted(guild.text_channels, key=lambda c: c.position):
                text_channels.append({
                    "id": ch.id,
                    "name": html_mod.escape(f"#{ch.name}"),
                    "selected": ch.id == channel_id,
                })

            guilds_data.append({
                "name": html_mod.escape(guild.name),
                "id": gid,
                "channel": channel_name,
                "channel_id": channel_id or 0,
                "cooldown": cooldown,
                "channels": text_channels,
            })

        # Also show guilds without config
        for guild in self.bot.guilds:
            if guild.id not in all_guilds:
                text_channels = []
                for ch in sorted(guild.text_channels, key=lambda c: c.position):
                    text_channels.append({
                        "id": ch.id,
                        "name": html_mod.escape(f"#{ch.name}"),
                        "selected": False,
                    })
                guilds_data.append({
                    "name": html_mod.escape(guild.name),
                    "id": guild.id,
                    "channel": "",
                    "channel_id": 0,
                    "cooldown": 60,
                    "channels": text_channels,
                })

        guilds_data.sort(key=lambda g: g["name"].lower())

        forbidden_escaped = [html_mod.escape(w) for w in forbidden_names]

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-id-badge"></i> AutoNick</h3>
  <p class="trini-tp-subtitle">Gestión de apodos automáticos y palabras prohibidas</p>

  {% for guild in guilds %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header">
      <h4>{{ guild.name }}</h4>
      {% if guild.channel %}
        <span class="badge bg-gradient-success">{{ guild.channel }}</span>
      {% else %}
        <span class="badge bg-gradient-secondary">Sin canal</span>
      {% endif %}
      <span class="badge bg-gradient-info ms-1">Cooldown: {{ guild.cooldown }}s</span>
    </div>

    <form method="POST" class="mt-3">
      <input type="hidden" name="action" value="update_settings">
      <input type="hidden" name="guild_id" value="{{ guild.id }}">
      <div class="row align-items-end">
        <div class="col-lg-4 col-md-6 mb-3">
          <label class="form-label text-xs mb-1">Canal de apodos</label>
          <select class="form-select form-select-sm" name="channel">
            <option value="">-- Desactivado --</option>
            {% for ch in guild.channels %}
            <option value="{{ ch.id }}" {{ "selected" if ch.selected }}>{{ ch.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-lg-3 col-md-4 mb-3">
          <label class="form-label text-xs mb-1">Cooldown (seg)</label>
          <input type="number" class="form-control form-control-sm" name="cooldown" value="{{ guild.cooldown }}" min="0" max="86400">
        </div>
        <div class="col-lg-2 col-12 mb-3">
          <button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100">
            <i class="fa fa-save me-1"></i> Guardar
          </button>
        </div>
      </div>
    </form>
  </div>
  {% endfor %}

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header">
      <h4><i class="fa fa-ban me-1"></i> Palabras Prohibidas</h4>
      <span class="badge bg-gradient-warning">{{ forbidden|length }} palabras</span>
    </div>

    <form method="POST" class="mt-3">
      <input type="hidden" name="action" value="add_forbidden">
      <div class="row align-items-end">
        <div class="col-lg-6 col-md-8 mb-3">
          <label class="form-label text-xs mb-1">Añadir palabra o frase prohibida</label>
          <input type="text" class="form-control form-control-sm" name="word" placeholder="Escribe la palabra..." maxlength="100" required>
        </div>
        <div class="col-lg-2 col-12 mb-3">
          <button type="submit" class="btn btn-xs bg-gradient-success mb-0 w-100">
            <i class="fa fa-plus me-1"></i> Añadir
          </button>
        </div>
      </div>
    </form>

    {% if forbidden|length > 0 %}
    <div class="table-responsive mt-2">
      <table class="table trini-table trini-tp-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Palabra / Frase</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {% for word in forbidden %}
          <tr>
            <td>{{ loop.index }}</td>
            <td><code>{{ word }}</code></td>
            <td>
              <form method="POST" style="display:inline">
                <input type="hidden" name="action" value="remove_forbidden">
                <input type="hidden" name="word" value="{{ word }}">
                <button type="submit" class="btn btn-xs bg-gradient-danger mb-0" onclick="return confirm('¿Eliminar esta palabra?')">
                  <i class="fa fa-trash"></i>
                </button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <p class="text-sm opacity-6 mt-2">No hay palabras prohibidas configuradas.</p>
    {% endif %}
  </div>
</div>
"""

        result = {
            "status": 0,
            "web_content": {
                "source": source,
                "guilds": guilds_data,
                "forbidden": forbidden_escaped,
            },
        }
        if notifications:
            result["notifications"] = notifications
        return result
