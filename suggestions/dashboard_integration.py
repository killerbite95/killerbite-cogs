"""
Dashboard integration for SimpleSuggestions.
Provides per-guild web interface for viewing and managing suggestions.
"""
import typing
import html as html_mod
from redbot.core import commands
from redbot.core.bot import Red

from .storage import SuggestionStatus, STATUS_CONFIG


def dashboard_page(*args, **kwargs):
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
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    async def cog_load(self) -> None:
        dashboard_cog = self.bot.get_cog("Dashboard")
        if dashboard_cog and hasattr(dashboard_cog, "rpc"):
            try:
                dashboard_cog.rpc.third_parties_handler.add_third_party(self)
            except Exception:
                pass

    @dashboard_page(
        name="suggestions",
        description="Ver y gestionar sugerencias",
        methods=("GET", "POST"),
    )
    async def rpc_suggestions_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Servidor no encontrado.</p></div>'}}

        method = kwargs.get("method", "GET")
        notifications = []

        # POST — change status
        if method == "POST":
            form = kwargs.get("data", {}).get("form", {})
            action = form.get("action", [""])[0] if isinstance(form.get("action"), list) else str(form.get("action", ""))

            if action == "update_status":
                sid_str = form.get("suggestion_id", ["0"])[0] if isinstance(form.get("suggestion_id"), list) else "0"
                new_status_str = form.get("new_status", [""])[0] if isinstance(form.get("new_status"), list) else ""
                reason = form.get("reason", [""])[0] if isinstance(form.get("reason"), list) else ""
                try:
                    sid = int(sid_str)
                    status_enum = SuggestionStatus(new_status_str)
                    await self.storage.update_status(guild, sid, status_enum, 0, reason or None)
                    notifications.append({"message": f"Sugerencia #{sid} actualizada a {STATUS_CONFIG.get(status_enum, {}).get('label', new_status_str)}.", "category": "success"})
                except Exception as e:
                    notifications.append({"message": f"Error: {e}", "category": "danger"})

        # GET — load THIS guild's suggestions
        try:
            data = await self.config.guild(guild).all()
        except Exception:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Error al cargar datos.</p></div>'}}

        suggestions_raw = data.get("suggestions", {})

        # Count by status
        status_counts = {}
        for st in SuggestionStatus:
            status_counts[st.value] = 0

        suggestions_list = []
        for sid, sdata in suggestions_raw.items():
            if not isinstance(sdata, dict):
                continue
            if sdata.get("deleted", False):
                continue
            status_val = str(sdata.get("status", "pending"))
            try:
                SuggestionStatus(status_val)
            except ValueError:
                status_val = "pending"
            if status_val in status_counts:
                status_counts[status_val] += 1

            author_id = int(sdata.get("author_id", 0) or 0)
            author_name = f"ID: {author_id}"
            member = guild.get_member(author_id)
            if member:
                author_name = str(member.display_name)
            else:
                user = self.bot.get_user(author_id)
                if user:
                    author_name = str(user.display_name)

            content = str(sdata.get("content", ""))
            preview = content[:120] + ("..." if len(content) > 120 else "")

            up = len(sdata.get("voters_up", []))
            down = len(sdata.get("voters_down", []))

            try:
                status_info = STATUS_CONFIG.get(SuggestionStatus(status_val), {})
            except ValueError:
                status_info = {"label": status_val, "emoji": ""}

            suggestions_list.append({
                "id": int(sid),
                "content": html_mod.escape(preview),
                "author": html_mod.escape(author_name),
                "upvotes": up,
                "downvotes": down,
                "score": up - down,
                "status": status_val,
                "status_label": str(status_info.get("label", status_val)),
                "status_emoji": str(status_info.get("emoji", "")),
                "reason": html_mod.escape(str(sdata.get("reason", "") or "")),
                "created_at": str(sdata.get("created_at", ""))[:10],
            })

        suggestions_list.sort(key=lambda s: s["id"], reverse=True)

        ch_id = data.get("suggestion_channel")
        ch_name = ""
        if ch_id:
            ch = guild.get_channel(ch_id)
            ch_name = f"#{ch.name}" if ch else ""

        total = len(suggestions_list)

        # Build status options
        statuses = []
        for st in SuggestionStatus:
            info = STATUS_CONFIG.get(st, {})
            statuses.append({
                "value": st.value,
                "label": str(info.get("label", st.value)),
                "emoji": str(info.get("emoji", "")),
            })

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-lightbulb-o"></i> Sugerencias</h3>
  <p class="trini-tp-subtitle">{{ total }} sugerencia{{ "s" if total != 1 else "" }}{% if channel %} en {{ channel }}{% endif %}</p>

  <div class="row mt-3 mb-3">
    {% for st in statuses %}
      {% set count = status_counts.get(st.value, 0) %}
      {% if count > 0 %}
      <div class="col-auto mb-1">
        <span class="badge bg-gradient-secondary">{{ st.emoji }} {{ st.label }}: {{ count }}</span>
      </div>
      {% endif %}
    {% endfor %}
  </div>

  {% if suggestions|length > 0 %}
  <div class="table-responsive">
    <table class="table trini-table trini-tp-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Contenido</th>
          <th>Autor</th>
          <th>Votos</th>
          <th>Estado</th>
          <th>Fecha</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        {% for s in suggestions %}
        <tr>
          <td><strong>{{ s.id }}</strong></td>
          <td title="{{ s.content }}">{{ s.content }}</td>
          <td>{{ s.author }}</td>
          <td>
            <span class="text-success">+{{ s.upvotes }}</span> /
            <span class="text-danger">-{{ s.downvotes }}</span>
            <small class="text-muted">({{ s.score }})</small>
          </td>
          <td><span class="badge bg-gradient-secondary">{{ s.status_emoji }} {{ s.status_label }}</span></td>
          <td><small>{{ s.created_at }}</small></td>
          <td>
            <a href="javascript:void(0)" onclick="toggleStatus('{{ s.id }}')" class="text-info text-xs font-weight-bold" title="Cambiar estado"><i class="fa fa-pencil"></i></a>
          </td>
        </tr>
        <tr id="status_{{ s.id }}" style="display:none">
          <td colspan="7" style="background:rgba(94,114,228,0.04)">
            <form method="POST" class="row align-items-end py-2 px-1">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <input type="hidden" name="action" value="update_status">
              <input type="hidden" name="suggestion_id" value="{{ s.id }}">
              <div class="col-lg-3 col-md-4 col-6 mb-2">
                <label class="form-label text-xs mb-1">Nuevo estado</label>
                <select class="form-select form-select-sm" name="new_status">
                  {% for st in statuses %}
                  <option value="{{ st.value }}" {{ "selected" if st.value == s.status }}>{{ st.emoji }} {{ st.label }}</option>
                  {% endfor %}
                </select>
              </div>
              <div class="col-lg-5 col-md-4 col-6 mb-2">
                <label class="form-label text-xs mb-1">Razón (opcional)</label>
                <input type="text" class="form-control form-control-sm" name="reason" placeholder="Motivo del cambio..." maxlength="500">
              </div>
              <div class="col-lg-2 col-12 mb-2">
                <button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100">
                  <i class="fa fa-save me-1"></i> Guardar
                </button>
              </div>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% if total > 50 %}
  <p class="text-xs text-muted">Mostrando las últimas 50 sugerencias de {{ total }}.</p>
  {% endif %}
  {% else %}
  <div class="trini-tp-empty">
    <i class="fa fa-lightbulb-o fa-3x"></i>
    <p>No hay sugerencias en este servidor.</p>
  </div>
  {% endif %}
</div>
<script>
function toggleStatus(s) {
  var r = document.getElementById('status_' + s);
  if (r) r.style.display = r.style.display === 'none' ? 'table-row' : 'none';
}
</script>
"""

        result = {
            "status": 0,
            "web_content": {
                "source": source,
                "suggestions": suggestions_list[:50],
                "statuses": statuses,
                "status_counts": status_counts,
                "total": total,
                "channel": ch_name,
            },
        }
        if notifications:
            result["notifications"] = notifications
        return result
