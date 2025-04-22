# arenaqueue/webhooks.py
# coding: utf-8

import aiohttp
import json
import hmac
import hashlib
import discord
from discord import Embed
from redbot.core import commands, Config

class WebhooksCog(commands.Cog):
    """🔗 Integración de Webhooks para enviar leaderboards al endpoint configurado."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7890123456)
        default_guild = {
            "webhook_url": None,
            "webhook_secret": None,
        }
        self.config.register_guild(**default_guild)

    @commands.group(name="premium", invoke_without_command=True)
    @commands.guild_only()
    async def premium(self, ctx: commands.Context):
        """Grupo de comandos premium (webhooks, banners, colores, etc.)"""
        await ctx.send_help(ctx.command)

    @premium.group(name="webhook_url", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def webhook_group(self, ctx: commands.Context):
        """Configura o elimina la URL del webhook para leaderboards."""
        await ctx.send_help(ctx.command)

    @webhook_group.command(name="set")
    async def webhook_set(self, ctx: commands.Context, url: str):
        """Establece la URL del webhook donde enviar los leaderboards."""
        secret = hashlib.sha256(url.encode()).hexdigest()[:32]
        await self.config.guild(ctx.guild).webhook_url.set(url)
        await self.config.guild(ctx.guild).webhook_secret.set(secret)
        embed = Embed(
            title="🔗 Webhook configurado",
            description=(
                f"URL establecida: {url}\n"
                f"Secret generado (32 chars): `{secret}`\n"
                "Guárdalo, no podrás recuperarlo de nuevo."
            ),
            colour=discord.Colour.green()
        )
        await ctx.send(embed=embed)

    @webhook_group.command(name="delete")
    async def webhook_delete(self, ctx: commands.Context):
        """Elimina la configuración del webhook."""
        await self.config.guild(ctx.guild).webhook_url.clear()
        await self.config.guild(ctx.guild).webhook_secret.clear()
        await ctx.send("🗑️ Configuración del webhook eliminada.")

    @commands.Cog.listener()
    async def on_game_end(self, guild_id: int, game: str, leaderboard: dict, season: dict = None):
        """
        Evento que otros cogs deben llamar al finalizar una partida.
        Envía payload al webhook configurado para el guild indicado.
        """
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        url = await self.config.guild(guild).webhook_url()
        secret = await self.config.guild(guild).webhook_secret()
        if not url or not secret:
            return
        payload = {"game": game, "leaderboard": leaderboard}
        if season is not None:
            payload["season"] = season
        body = json.dumps(payload)
        headers = {
            "Content-Type": "application/json",
            "Webhook-Secret": secret
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=body, headers=headers) as resp:
                    if resp.status != 200:
                        channel = discord.utils.get(self.bot.get_all_channels(), name="admin-log")
                        if channel:
                            await channel.send(f"❌ Error al enviar webhook: {resp.status}")
            except Exception as e:
                channel = discord.utils.get(self.bot.get_all_channels(), name="admin-log")
                if channel:
                    await channel.send(f"❌ Excepción al enviar webhook: {e}")

    async def verify_webhook(self, guild: discord.Guild, request_headers: dict, payload_body: bytes) -> bool:
        """Verifica un webhook entrante comparando el header 'Webhook-Secret'."""
        secret = await self.config.guild(guild).webhook_secret()
        incoming = request_headers.get("Webhook-Secret")
        if not incoming or not secret:
            return False
        return hmac.compare_digest(incoming, secret)
