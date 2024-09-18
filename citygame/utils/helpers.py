# utils/helpers.py

import importlib
import os
import discord
import logging

log = logging.getLogger("red.citygame")

def validate_role(role: str) -> str:
    """Valida y normaliza el rol ingresado por el usuario.

    Args:
        role: El rol ingresado por el usuario.

    Returns:
        El rol normalizado ('mafia', 'civil', 'policia') o None si es inválido.
    """
    role = role.lower()
    roles_map = {
        'mafia': 'mafia',
        'civil': 'civil',
        'civilian': 'civil',
        'policia': 'policia',
        'policía': 'policia',
        'police': 'policia',
    }
    return roles_map.get(role)


async def get_translations(cog, member):
    """Obtiene las traducciones para el idioma del miembro.

    Args:
        cog: La instancia del cog.
        member: El miembro para quien obtener las traducciones.

    Returns:
        Un diccionario con las traducciones.
    """
    language = await get_language(cog, member)
    if language not in cog.translations_cache:
        try:
            module = importlib.import_module(f"..locales.{language}", package=__package__)
            cog.translations_cache[language] = module.translations
        except ImportError:
            module = importlib.import_module(f"..locales.es", package=__package__)
            cog.translations_cache[language] = module.translations
    return cog.translations_cache[language]


def get_asset(filename: str) -> str:
    """Obtiene la ruta de un archivo de imagen para usar en embeds.

    Args:
        filename: El nombre del archivo de imagen.

    Returns:
        Una cadena con la ruta del archivo para usar en embeds.
    """
    return f"attachment://{filename}"


async def update_experience(cog, member, xp_gain: int, translations):
    """Actualiza la experiencia y el nivel de un miembro.

    Args:
        cog: La instancia del cog.
        member: El miembro a actualizar.
        xp_gain: La cantidad de experiencia ganada.
        translations: Las traducciones correspondientes.
    """
    member_config = cog.config.member(member)
    xp = await member_config.xp() + xp_gain
    level = await member_config.level()
    if xp >= level * 100:
        level += 1
        xp = 0
        await member_config.level.set(level)
        embed = discord.Embed(
            title=translations["level_up_title"],
            description=translations["level_up"].format(level=level),
            color=discord.Color.gold()
        )
        await member.send(embed=embed)
    await member_config.xp.set(xp)


async def get_language(cog, member) -> str:
    """Obtiene el idioma preferido del usuario.

    Si el usuario no ha establecido un idioma, intenta detectar el idioma
    basado en la configuración de Discord.

    Args:
        cog: La instancia del cog.
        member: El miembro para quien obtener el idioma.

    Returns:
        Una cadena con el código del idioma ('es' o 'en').
    """
    language = await cog.config.member(member).language()
    if language:
        return language
    else:
        # Intentar detectar el idioma del usuario
        user_locale = getattr(member, 'locale', 'en-US')
        language = user_locale[:2]
        if language not in ['es', 'en']:
            language = 'en'
        return language

async def send_embed_with_image(ctx, embed, image_filename, asset_path):
    """Envía un embed con una imagen opcional.

    Args:
        ctx: Contexto del comando.
        embed: El objeto Embed a enviar.
        image_filename: El nombre del archivo de imagen.
        asset_path: La ruta a la carpeta de assets.
    """
    file_path = os.path.join(asset_path, image_filename)
    if os.path.isfile(file_path):
        embed.set_thumbnail(url=get_asset(image_filename))
        file = discord.File(file_path, filename=image_filename)
        await ctx.send(embed=embed, file=file)
    else:
        # Registrar que la imagen no se encontró
        log.warning(f"Archivo de imagen no encontrado: {file_path}")
        await ctx.send(embed=embed)
