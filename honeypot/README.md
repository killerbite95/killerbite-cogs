# Honeypot

Crea un canal trampa arriba del todo del servidor. Los selfbots y cuentas de scam que escriben ahi se notifican, silencian, expulsan o banean al instante.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs honeypot
!load honeypot
```

**Requisitos:** Dependencia `AAA3A_utils` (`!pipinstall git+https://github.com/AAA3A-AAA3A/AAA3A_utils.git`). Solo el **owner del servidor** lo configura.

## Puesta en marcha paso a paso

1. Crea el canal trampa: `!sethoneypot createchannel`. Se crea arriba del todo con un aviso de "no escribas aqui".
2. Canal de registros: `!sethoneypot logschannel #logs-honeypot`.
3. Rol a mencionar cuando caiga alguien: `!sethoneypot pingrole @Staff`.
4. Que hacer con quien escriba: `!sethoneypot action ban` (`mute`, `kick` o `ban`). Si eliges `mute`, indica el rol: `!sethoneypot muterole @Silenciado`.
5. (Opcional, si banea) Dias de mensajes a borrar: `!sethoneypot bandeletemessagedays 3`.
6. Activalo: `!sethoneypot enabled true`.
7. Comprueba que no falta nada: `!sethoneypot diagnose`.

Alternativa: `!sethoneypot modalconfig` configura todo de golpe en un formulario. Si borras el aviso del canal, `!sethoneypot resend` lo vuelve a publicar.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!sethoneypot action <action>` | The action to take when a self bot/scammer is detected. | Owner del servidor |
| `!sethoneypot bandeletemessagedays <ban_delete_message_days>` | The number of days of messages to delete when banning a self bot/scammer. | Owner del servidor |
| `!sethoneypot createchannel` | Create the honeypot channel. Alias: `makechannel`. | Owner del servidor |
| `!sethoneypot diagnose` | Check the setup and report everything that prevents the honeypot from working. Alias: `check`, `debug`. | Owner del servidor |
| `!sethoneypot enabled <enabled>` | Toggle the cog. | Owner del servidor |
| `!sethoneypot logschannel <logs_channel>` | The channel to send the logs to. | Owner del servidor |
| `!sethoneypot modalconfig [confirmation=False]` | Set all settings for the cog with a Discord Modal. Alias: `configmodal`. | Owner del servidor |
| `!sethoneypot muterole <role>` | The mute role to assign to the self bots/scammers, if the action is `mute`. | Owner del servidor |
| `!sethoneypot pingrole <role>` | The role to ping when a self bot/scammer is detected. | Owner del servidor |
| `!sethoneypot resend` | Resend the honeypot embed (deletes the old one and sends a new one). | Owner del servidor |
| `!sethoneypot resetsetting <setting>` | Reset a setting. | Owner del servidor |
| `!sethoneypot showsettings [with_dev=False]` | Show all settings for the cog with defaults and values. | Owner del servidor |
