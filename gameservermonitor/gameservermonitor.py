import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, Minecraft
import datetime
import pytz
import logging
import re
import typing

# Importamos la integración del dashboard
from .dashboard_integration import DashboardIntegration, dashboard_page

# Configuración de logging
logger = logging.getLogger("red.trini.gameservermonitor")

def extract_numeric_version(version_str: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)+)", version_str)
    if m:
        return m.group(1)
    return version_str

SUPPORTED_SOURCE_GAMES = {"cs2", "css", "gmod", "rust", "dayz"}

class GameServerMonitor(DashboardIntegration, commands.Cog):
    """Monitoriza servidores de juegos y actualiza su estado en Discord. By Killerbite95"""
    __author__ = "Killerbite95"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "servers": {},
            "timezone": "UTC",
            "refresh_time": 60
        }
        self.config.register_guild(**default_guild)
        self.debug = False
        self.server_monitor.start()

    # -------------------- Comandos --------------------

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, timezone: str):
        """Establece la zona horaria para las actualizaciones."""
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await ctx.send(f"La zona horaria '{timezone}' no es válida.")
            return
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(f"Zona horaria establecida en {timezone}")

    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(
        self,
        ctx,
        server_ip: str,
        game: str,
        game_port: typing.Optional[int] = None,
        query_port: typing.Optional[int] = None,
        channel: typing.Optional[discord.TextChannel] = None,
        domain: typing.Optional[str] = None,
    ):
        """
        Añade un servidor para monitorear su estado.

        Uso general (no DayZ):
          !addserver <ip[:puerto]> <juego> [#canal] [dominio]

        Uso DayZ (requiere puertos explícitos):
          !addserver <ip> dayz <game_port> <query_port> [#canal] [dominio]
        """
        channel = channel or ctx.channel
        game = (game or "").lower().strip()

        # --- DayZ: requiere game_port + query_port ---
        if game == "dayz":
            host = server_ip.split(":")[0]  # tolera ip:algo, usa solo host
            if game_port is None or query_port is None:
                return await ctx.send(
                    "Para **DayZ** indica `game_port` (entrada, ej. 2302) y `query_port` (consulta, ej. 27016).\n"
                    "Ejemplo: `!addserver 1.2.3.4 dayz 2302 27016 #canal`"
                )
            if not self._valid_port(game_port) or not self._valid_port(query_port):
                return await ctx.send("`game_port` y `query_port` deben estar entre 1 y 65535.")

            key = f"{host}:{int(game_port)}"  # la clave visible siempre usa el puerto de juego
            async with self.config.guild(ctx.guild).servers() as servers:
                if key in servers:
                    return await ctx.send(f"El servidor {key} ya está siendo monitoreado.")
                servers[key] = {
                    "game": "dayz",
                    "channel_id": channel.id,
                    "message_id": None,
                    "domain": (domain or None),
                    "game_port": int(game_port),
                    "query_port": int(query_port),
                }

            await ctx.send(
                f"Servidor **{key}** (DayZ) añadido en {channel.mention}."
                f"\nPuertos → juego: **{game_port}**, query: **{query_port}**"
                + (f"\nDominio asignado: {domain}" if domain else "")
            )
            return await self.update_server_status(ctx.guild, key, first_time=True)

        # --- Resto de juegos ---
        parsed = self.parse_server_ip(server_ip, game)
        if not parsed:
            await ctx.send(f"Formato inválido para server_ip '{server_ip}'. Debe ser 'ip:puerto' o solo 'ip'.")
            return
        ip_part, port_part, server_ip_formatted = parsed

        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip_formatted in servers:
                await ctx.send(f"El servidor {server_ip_formatted} ya está siendo monitoreado.")
                return
            servers[server_ip_formatted] = {
                "game": game,
                "channel_id": channel.id,
                "message_id": None,
                "domain": domain
            }
        await ctx.send(
            f"Servidor {server_ip_formatted} añadido para el juego **{game.upper()}** en {channel.mention}."
            + (f"\nDominio asignado: {domain}" if domain else "")
        )
        await self.update_server_status(ctx.guild, server_ip_formatted, first_time=True)

    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, server_key: str):
        """Elimina el monitoreo de un servidor. Pasa exactamente la clave listada (ej. `ip:puerto_de_juego`)."""
        if ":" not in server_key:
            await ctx.send("Debes indicar `ip:puerto` tal como aparece en la lista.")
            return

        async with self.config.guild(ctx.guild).servers() as servers:
            if server_key in servers:
                del servers[server_key]
                await ctx.send(f"Monitoreo del servidor {server_key} eliminado.")
            else:
                await ctx.send(f"No se encontró un servidor con clave {server_key}.")

    @commands.command(name="forzarstatus")
    async def force_status(self, ctx):
        """Fuerza una actualización de estado en el canal actual."""
        servers = await self.config.guild(ctx.guild).servers()
        actualizados = False
        for server_key, data in servers.items():
            if data.get("channel_id") == ctx.channel.id:
                await self.update_server_status(ctx.guild, server_key, first_time=True)
                actualizados = True
        if actualizados:
            await ctx.send("Actualización de estado forzada para los servidores en este canal.")
        else:
            await ctx.send("No hay servidores monitoreados en este canal.")

    @commands.command(name="listaserver")
    async def list_servers(self, ctx):
        """Lista todos los servidores monitoreados."""
        servers = await self.config.guild(ctx.guild).servers()
        if not servers:
            await ctx.send("No hay servidores siendo monitoreados.")
            return
        lines = ["Servidores monitoreados:"]
        for server_key, data in servers.items():
            channel = self.bot.get_channel(data.get("channel_id"))
            domain = data.get("domain")
            game = (data.get("game") or "N/A").upper()
            extra = ""
            if (data.get("game") or "").lower().strip() == "dayz":
                extra = f" (game:{data.get('game_port')} | query:{data.get('query_port')})"
            line = f"**{server_key}** - Juego: **{game}**{extra} - Canal: {channel.mention if channel else 'Desconocido'}"
            if domain:
                line += f" - Dominio: {domain}"
            lines.append(line)
        await ctx.send("\n".join(lines))

    @commands.command(name="refreshtime")
    @checks.admin_or_permissions(administrator=True)
    async def refresh_time(self, ctx, seconds: int):
        """Establece el tiempo de actualización en segundos."""
        if seconds < 10:
            await ctx.send("El tiempo de actualización debe ser al menos 10 segundos.")
            return
        await self.config.guild(ctx.guild).refresh_time.set(seconds)
        self.server_monitor.change_interval(seconds=seconds)
        await ctx.send(f"Tiempo de actualización establecido en {seconds} segundos.")

    @commands.command(name="gameservermonitordebug")
    @checks.admin_or_permissions(administrator=True)
    async def gameservermonitordebug(self, ctx, state: bool):
        """Activa o desactiva el modo debug."""
        self.debug = state
        await ctx.send(f"Modo debug {'activado' if state else 'desactivado'}.")

    # -------------------- Tareas --------------------

    @tasks.loop(seconds=60)
    async def server_monitor(self):
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            for server_key in servers.keys():
                await self.update_server_status(guild, server_key)

    @server_monitor.before_loop
    async def before_server_monitor(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            refresh_time = await self.config.guild(guild).refresh_time()
            self.server_monitor.change_interval(seconds=refresh_time)

    # -------------------- Utilidades --------------------

    def _valid_port(self, port: int) -> bool:
        return isinstance(port, int) and 1 <= port <= 65535

    def parse_server_ip(self, server_ip: str, game: str = None):
        """
        Para juegos NO DayZ:
        - Acepta 'ip:puerto' o solo 'ip' y usa puerto por defecto según el juego.
        Para DayZ, este método NO se usa; los puertos se pasan explícitamente.
        """
        default_ports = {
            "cs2": 27015,
            "css": 27015,
            "gmod": 27015,
            "rust": 28015,
            "minecraft": 25565,
        }
        if ":" in server_ip:
            parts = server_ip.split(":")
            if len(parts) != 2:
                logger.error(f"server_ip '{server_ip}' tiene más de un ':'.")
                return None
            ip_part, port_str = parts
            try:
                port_part = int(port_str)
            except ValueError:
                logger.error(f"Puerto inválido '{port_str}' en server_ip '{server_ip}'.")
                return None
        else:
            if not game:
                logger.error(f"server_ip '{server_ip}' no incluye puerto y no se proporcionó el juego.")
                return None
            port_part = default_ports.get((game or "").lower().strip())
            if not port_part:
                logger.error(f"No hay puerto predeterminado para el juego '{game}'.")
                return None
            ip_part = server_ip
        return ip_part, port_part, f"{ip_part}:{port_part}"

    def convert_motd(self, motd):
        if isinstance(motd, str):
            text = motd.strip()
        elif isinstance(motd, dict):
            text = motd.get("text", "")
            if "extra" in motd and isinstance(motd["extra"], list):
                for extra in motd["extra"]:
                    text += " " + self.convert_motd(extra)
            text = text.strip()
        elif isinstance(motd, list):
            text = " ".join([self.convert_motd(item) for item in motd]).strip()
        else:
            text = ""
        return " ".join(text.split())

    def truncate_title(self, title: str, suffix: str) -> str:
        max_total = 256
        allowed = max_total - len(suffix)
        if len(title) > allowed:
            title = title[: max(allowed - 3, 0)] + "..."
        return title + suffix

    # -------------------- Core --------------------

    async def _try_dayz_query(self, host: str, candidates: typing.List[int]) -> typing.Tuple[typing.Optional[int], typing.Optional[typing.Any]]:
        """
        Intenta consultar DayZ con una lista de puertos de query.
        Devuelve (puerto_exitoso, info) o (None, None) si todos fallan.
        """
        for qp in candidates:
            try:
                s = Source(host=host, port=int(qp))
                info = await s.get_info()
                return qp, info
            except Exception as e:
                logger.debug(f"DayZ query falló en {host}:{qp} → {e!r}")
        return None, None

    async def update_server_status(self, guild, server_key, first_time=False):
        async with self.config.guild(guild).servers() as servers:
            server_info = servers.get(server_key)
            if not server_info:
                logger.warning(f"Servidor {server_key} no encontrado en {guild.name}.")
                return

            game = (server_info.get("game") or "").lower().strip()
            channel = self.bot.get_channel(server_info.get("channel_id"))
            message_id = server_info.get("message_id")
            domain = server_info.get("domain")

            if not channel:
                logger.error(f"Canal no encontrado en {guild.name} (ID {server_info.get('channel_id')}).")
                return

            # Resolver host y datos base
            if game == "dayz":
                host = server_key.split(":")[0]
                game_port = int(server_info.get("game_port") or server_key.split(":")[1])
                query_port = server_info.get("query_port")
                public_ip = "178.33.160.187" if host.startswith("10.0.0.") else host
                game_name = "DayZ Standalone"
                ip_to_show = f"{public_ip}:{game_port}"
                # No hagas query aquí: se hará dentro del try/except de abajo
                resolver = ("dayz", host, game_port, query_port)
            else:
                parsed_ip, parsed_port = server_key.split(":")
                public_ip = "178.33.160.187" if parsed_ip.startswith("10.0.0.") else parsed_ip
                ip_to_show = f"{public_ip}:{parsed_port}"

                if game in {"cs2", "css", "gmod", "rust"}:
                    game_name = {
                        "cs2": "Counter-Strike 2",
                        "css": "Counter-Strike: Source",
                        "gmod": "Garry's Mod",
                        "rust": "Rust",
                    }.get(game, "Unknown Game")
                    resolver = ("source", parsed_ip, int(parsed_port))
                elif game == "minecraft":
                    game_name = "Minecraft"
                    resolver = ("minecraft", parsed_ip, int(parsed_port))
                else:
                    logger.warning(f"Juego '{game}' no soportado para el servidor {server_key}.")
                    return

            try:
                # --------- Query (todo dentro del try) ---------
                if resolver[0] == "minecraft":
                    _ip, _port = resolver[1], resolver[2]
                    s_mc = Minecraft(host=_ip, port=_port)
                    info = await s_mc.get_status()
                    if self.debug:
                        logger.debug(f"Raw get_status para {server_key}: {info}")
                    is_passworded = False
                    players = info["players"]["online"]
                    max_players = info["players"]["max"]
                    raw_motd = info.get("description", "Minecraft Server")
                    hostname = self.convert_motd(raw_motd)
                    version_str = info.get("version", {}).get("name", "???")
                    map_name = extract_numeric_version(version_str)
                elif resolver[0] == "source":
                    _ip, _port = resolver[1], resolver[2]
                    s_src = Source(host=_ip, port=_port)
                    info = await s_src.get_info()
                    if self.debug:
                        logger.debug(f"Raw get_info para {server_key}: {info}")
                    players = getattr(info, "players", 0)
                    max_players = getattr(info, "max_players", 0)
                    map_name = getattr(info, "map", "N/A")
                    hostname = getattr(info, "name", "Unknown Server")
                    is_passworded = hasattr(info, "visibility") and info.visibility == 1
                else:  # dayz
                    host, game_port, query_port = resolver[1], resolver[2], resolver[3]
                    info = None
                    # Intento de inferencia si no hay query_port guardado
                    if query_port is None:
                        candidates = [27016, game_port + 1, game_port + 2]
                        qp_ok, info = await self._try_dayz_query(host, candidates)
                        if qp_ok is not None:
                            query_port = int(qp_ok)
                            servers[server_key]["query_port"] = query_port
                            servers[server_key]["game_port"] = int(game_port)
                            logger.info(f"DayZ {host}: inferido query_port={query_port}")
                    # Si ya tenemos puerto, o la inferencia no devolvió info, consulta directa
                    if info is None and query_port is not None:
                        s_src = Source(host=host, port=int(query_port))
                        info = await s_src.get_info()

                    if self.debug:
                        logger.debug(f"Raw get_info (DayZ) para {server_key}: {info}")
                    players = getattr(info, "players", 0)
                    max_players = getattr(info, "max_players", 0)
                    map_name = getattr(info, "map", "N/A")
                    hostname = getattr(info, "name", "Unknown Server")
                    is_passworded = hasattr(info, "visibility") and info.visibility == 1

                if not hostname:
                    hostname = "Minecraft Server" if resolver[0] == "minecraft" else "Game Server"

                # --------- Embed OK ---------
                timezone = await self.config.guild(guild).timezone()
                try:
                    tz = pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    logger.error(f"Zona horaria '{timezone}' inválida en {guild.name}, usando UTC.")
                    tz = pytz.UTC
                local_time = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

                suffix = " - Server Status"
                title = self.truncate_title(hostname, suffix)
                embed = discord.Embed(
                    title=title,
                    color=(discord.Color.orange() if is_passworded else discord.Color.green())
                )
                embed.add_field(
                    name=("🔐 Status" if is_passworded else "✅ Status"),
                    value=("Maintenance" if is_passworded else "Online"),
                    inline=True
                )
                embed.add_field(name="🎮 Game", value=game_name, inline=True)

                if resolver[0] != "minecraft":
                    connect_url = f"https://alienhost.ovh/connect.php?ip={ip_to_show}"
                    embed.add_field(name="\n\u200b\n🔗 Connect", value=f"[Connect]({connect_url})\n\u200b\n", inline=False)

                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
                if resolver[0] == "minecraft":
                    embed.add_field(name="💎 Version", value=map_name, inline=True)
                else:
                    embed.add_field(name="🗺️ Current Map", value=map_name, inline=True)

                percent = int(players / max_players * 100) if max_players > 0 else 0
                embed.add_field(name="👥 Players", value=f"{players}/{max_players} ({percent}%)", inline=True)
                embed.set_footer(text=f"Game Server Monitor by Killerbite95 | Last update: {local_time}")

                if first_time or not message_id:
                    msg = await channel.send(embed=embed)
                    servers[server_key]["message_id"] = msg.id
                else:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(embed=embed)

            except Exception as e:
                # --------- Fallback OFFLINE ---------
                logger.error(f"Error actualizando {server_key}: {e!r}")
                fallback_title = self.truncate_title((game_name if 'game_name' in locals() else 'Game') + " Server", " - ❌ Offline")
                embed = discord.Embed(title=fallback_title, color=discord.Color.red())
                embed.add_field(name="Status", value="🔴 Offline", inline=True)
                embed.add_field(name="🎮 Game", value=(game_name if 'game_name' in locals() else game.upper()), inline=True)

                # IP a mostrar en fallo
                if game == "dayz":
                    host = server_key.split(":")[0]
                    gp = int(server_info.get("game_port") or server_key.split(":")[1])
                    ip_to_show = f"{('178.33.160.187' if host.startswith('10.0.0.') else host)}:{gp}"
                else:
                    ip_to_show = f"{('178.33.160.187' if server_key.split(':')[0].startswith('10.0.0.') else server_key.split(':')[0])}:{server_key.split(':')[1]}"

                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
                if game != "minecraft":
                    connect_url = f"https://alienhost.ovh/connect.php?ip={ip_to_show}"
                    embed.add_field(name="\n\u200b\n🔗 Connect", value=f"[Connect]({connect_url})\n\u200b\n", inline=False)
                embed.set_footer(text="Game Server Monitor by Killerbite95")

                if first_time or not message_id:
                    msg = await channel.send(embed=embed)
                    servers[server_key]["message_id"] = msg.id
                else:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(embed=embed)

    # -------------------- Dashboard --------------------

    @dashboard_page(name="servers", description="Muestra los servidores monitorizados")
    async def rpc_callback_servers(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}

        servers = await self.config.guild(guild).servers()

        html_content = """
        <link rel="stylesheet"
              href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <div class="container mt-4">
          <h1 class="mb-4">Servidores Monitorizados</h1>
          <table class="table table-bordered table-striped">
            <thead class="table-dark">
              <tr>
                <th scope="col">IP (clave)</th>
                <th scope="col">Juego</th>
                <th scope="col">Canal ID</th>
                <th scope="col">Dominio</th>
                <th scope="col">Puertos</th>
              </tr>
            </thead>
            <tbody>
        """
        for server_key, data in servers.items():
            game = (data.get("game") or "N/A").upper()
            channel_id = data.get("channel_id", "N/A")
            domain = data.get("domain", "N/A") or "N/A"
            ports = "-"
            if (data.get("game") or "").lower().strip() == "dayz":
                ports = f"game:{data.get('game_port')} | query:{data.get('query_port')}"
            html_content += f"""
              <tr>
                <td>{server_key}</td>
                <td>{game}</td>
                <td>{channel_id}</td>
                <td>{domain}</td>
                <td>{ports}</td>
              </tr>
            """
        html_content += """
            </tbody>
          </table>
        </div>
        """
        return {"status": 0, "web_content": {"source": html_content}}

    @dashboard_page(name="add_server", description="Añade un servidor al monitor", methods=("GET", "POST"))
    async def rpc_add_server(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """Página del dashboard para añadir un servidor. Para DayZ, indica game_port y query_port."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        import wtforms

        class AddServerForm(kwargs["Form"]):
            server_ip = wtforms.StringField("Server Host (IP o dominio, opcional ':puerto' salvo DayZ)", validators=[wtforms.validators.InputRequired()])
            game = wtforms.StringField("Juego (cs2, css, gmod, rust, minecraft, dayz)", validators=[wtforms.validators.InputRequired()])
            game_port = wtforms.IntegerField("DayZ Game Port (ej. 2302)", default=None)
            query_port = wtforms.IntegerField("DayZ Query Port (ej. 27016)", default=None)
            channel_id = wtforms.IntegerField("Channel ID", validators=[wtforms.validators.InputRequired()])
            domain = wtforms.StringField("Dominio (opcional)")
            submit = wtforms.SubmitField("Añadir Servidor")

        form = AddServerForm()
        if form.validate_on_submit():
            server_ip = form.server_ip.data.strip()
            game = form.game.data.strip().lower()
            channel_id = form.channel_id.data
            domain = form.domain.data.strip() if form.domain.data else None

            if game == "dayz":
                gp = form.game_port.data
                qp = form.query_port.data
                if gp in (None, "") or qp in (None, ""):
                    return {"status": 1, "error": "Para DayZ debes indicar game_port y query_port."}
                if not self._valid_port(int(gp)) or not self._valid_port(int(qp)):
                    return {"status": 1, "error": "Puertos inválidos (1-65535)."}
                host = server_ip.split(":")[0]
                key = f"{host}:{int(gp)}"
                async with self.config.guild(guild).servers() as servers:
                    if key in servers:
                        return {"status": 0, "notifications": [{"message": "El servidor ya está siendo monitoreado.", "category": "warning"}]}
                    servers[key] = {
                        "game": "dayz",
                        "channel_id": channel_id,
                        "message_id": None,
                        "domain": domain,
                        "game_port": int(gp),
                        "query_port": int(qp),
                    }
                await self.update_server_status(guild, key, first_time=True)
                return {
                    "status": 0,
                    "notifications": [{"message": f"Servidor {key} (DayZ) añadido correctamente.", "category": "success"}],
                    "redirect_url": kwargs["request_url"],
                }

            parsed = self.parse_server_ip(server_ip, game)
            if not parsed:
                return {"status": 1, "error": "Formato de server_ip inválido o juego sin puerto por defecto."}
            ip_part, port_part, server_ip_formatted = parsed

            async with self.config.guild(guild).servers() as servers:
                if server_ip_formatted in servers:
                    return {"status": 0, "notifications": [{"message": "El servidor ya está siendo monitoreado.", "category": "warning"}]}
                servers[server_ip_formatted] = {
                    "game": game,
                    "channel_id": channel_id,
                    "message_id": None,
                    "domain": domain
                }
            await self.update_server_status(guild, server_ip_formatted, first_time=True)
            return {
                "status": 0,
                "notifications": [{"message": f"Servidor {server_ip_formatted} añadido correctamente.", "category": "success"}],
                "redirect_url": kwargs["request_url"],
            }

        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}

    @dashboard_page(name="remove_server", description="Elimina un servidor del monitor", methods=("GET", "POST"))
    async def rpc_remove_server(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """Página del dashboard para eliminar un servidor. Indica la clave exacta (ip:puerto_de_juego)."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        import wtforms

        class RemoveServerForm(kwargs["Form"]):
            server_key = wtforms.StringField("Server Key (ip:puerto_de_juego)", validators=[wtforms.validators.InputRequired()])
            submit = wtforms.SubmitField("Eliminar Servidor")

        form = RemoveServerForm()
        if form.validate_on_submit():
            key = form.server_key.data.strip()
            async with self.config.guild(guild).servers() as servers:
                if key not in servers:
                    return {"status": 0, "notifications": [{"message": "El servidor no está siendo monitoreado.", "category": "warning"}]}
                del servers[key]
            return {
                "status": 0,
                "notifications": [{"message": f"Servidor {key} eliminado correctamente.", "category": "success"}],
                "redirect_url": kwargs["request_url"],
            }

        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}

def setup(bot):
    cog = GameServerMonitor(bot)
    bot.add_cog(cog)
    try:
        from .dashboard_integration import DashboardIntegration
    except ImportError:
        import dashboard_integration
        DashboardIntegration = dashboard_integration.DashboardIntegration
    DashboardIntegration(bot, cog.config)
