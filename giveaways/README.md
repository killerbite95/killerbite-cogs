# Giveaways

Sorteos con boton, requisitos, presets reutilizables e historial.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs giveaways
!load giveaways
```

**Requisitos:** Dependencia `dateparser` (se instala con el cog). Requiere **Gestionar servidor**.

## Puesta en marcha paso a paso

1. Revisa los ajustes por defecto: `!gw set show`. Cambia los que quieras, por ejemplo `!gw set buttontext Participar`, `!gw set emoji 🎁` o `!gw set congratulate true` (DM a los ganadores).
2. Crea un sorteo sencillo (premio, duracion, ganadores, canal): `!gw create "Nitro Classic" 1d 1 #sorteos`.
   Alternativa rapida: `!gw start #sorteos 2h Llavero oficial`.
3. Sorteos con requisitos (roles, nivel, antiguedad...): lee `!gw explain` y usa `!gw advanced <argumentos>`.
4. Guarda plantillas para repetir: `!gw preset save semanal <argumentos>` y lanzalas con `!gw preset use semanal`.
5. Gestion: `!gw list`, `!gw end <id_mensaje>`, `!gw reroll <id_mensaje>`, `!gw cancel <id_mensaje>`, `!gw entrants <id_mensaje>`.
6. Guia completa dentro de Discord: `!gw guide`.

## Dashboard

Pagina **giveaways**: sorteos activos e historial. Mods y admins.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!gw advanced <arguments>` | Advanced creation of Giveaways. Alias: `adv`. | Permiso Gestionar servidor |
| `!gw cancel <msgid>` | Cancel a giveaway without drawing winners. | Permiso Gestionar servidor |
| `!gw cleanup` | Remove all ended giveaways from the config for this server. | Permiso Gestionar servidor |
| `!gw create <prize> <duration> [winners=1] [channel] [description]` | Create a giveaway with simple parameters. | Permiso Gestionar servidor |
| `!gw delete <msgid>` | Delete a specific giveaway from the config. | Permiso Gestionar servidor |
| `!gw edit <msgid> <flags>` | Edit a giveaway. | Permiso Gestionar servidor |
| `!gw end <msgid>` | End a giveaway. | Permiso Gestionar servidor |
| `!gw entrants <msgid>` | List all entrants for a giveaway (active or ended). | Permiso Gestionar servidor |
| `!gw explain` | Explanation of giveaway advanced and the arguments it supports. | Permiso Gestionar servidor |
| `!gw guide` | 📖 Full guide for the Giveaway system. | Permiso Gestionar servidor |
| `!gw history` | View recent giveaway history (last 50). | Permiso Gestionar servidor |
| `!gw info <msgid>` | Information about a giveaway (active or ended). | Permiso Gestionar servidor |
| `!gw integrations` | Various 3rd party integrations for giveaways. | Permiso Gestionar servidor |
| `!gw list` | List all giveaways in the server. | Permiso Gestionar servidor |
| `!gw preset delete <name>` | Delete a saved preset. | Permiso Gestionar servidor |
| `!gw preset list` | List all saved presets. | Permiso Gestionar servidor |
| `!gw preset save <name> <flags>` | Save a giveaway preset. Use the same flags as `gw advanced`. | Permiso Gestionar servidor |
| `!gw preset use <name> [extra_flags]` | Use a preset to create a giveaway. | Permiso Gestionar servidor |
| `!gw reroll <msgid>` | Reroll a giveaway. | Permiso Gestionar servidor |
| `!gw set announce <enabled>` | Set whether to post a separate announcement when a giveaway ends. | Permiso Gestionar servidor |
| `!gw set buttonstyle <style>` | Set the default button style. Options: green, blurple, grey, red. | Permiso Gestionar servidor |
| `!gw set buttontext <text>` | Set the default button text for giveaways. | Permiso Gestionar servidor |
| `!gw set congratulate <enabled>` | Set whether to DM winners by default. | Permiso Gestionar servidor |
| `!gw set emoji <emoji>` | Set the default emoji for giveaways. | Permiso Gestionar servidor |
| `!gw set notify <enabled>` | Set whether to DM users when they fail to enter by default. | Permiso Gestionar servidor |
| `!gw set show` | Show current default giveaway settings. | Permiso Gestionar servidor |
| `!gw set showrequirements <enabled>` | Set whether to show requirements on the embed by default. | Permiso Gestionar servidor |
| `!gw set updatebutton <enabled>` | Set whether to update the button with entrant count by default. | Permiso Gestionar servidor |
| `!gw start [channel] <time> <prize>` | Start a giveaway. | Permiso Gestionar servidor |
