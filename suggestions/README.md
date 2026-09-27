# Suggestions

Sistema de sugerencias con botones de voto, hilos, estados (pendiente, en revision, planificada, en progreso, aprobada, implementada, denegada, duplicada) y aviso al autor.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs suggestions
!load suggestions
```

**Requisitos:** Solo administradores configuran; el staff gestiona las sugerencias.

## Puesta en marcha paso a paso

1. Canal donde se publican: `!suggestset channel #sugerencias`.
2. (Opcional) Canal de registro: `!suggestset logchannel #logs-sugerencias`.
3. Rol de staff que puede aprobar o denegar: `!suggestset staffrole @Staff`.
4. (Opcional) Ajustes: `!suggestset buttons` (botones o reacciones), `!suggestset threads` (hilo por sugerencia), `!suggestset autoarchive`, `!suggestset notify` (avisar al autor).
5. Revisa todo: `!suggestset settings`.
6. Los usuarios sugieren con `!suggest <texto>` (o `/suggest`, que abre un formulario).
7. El staff responde con `!approve <id> <motivo>`, `!deny <id> <motivo>` o `!setstatus <id> in_review|planned|in_progress|implemented|duplicate <motivo>`.

Mas detalle en [DOCUMENTATION.md](DOCUMENTATION.md).

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!approve <reference> [reason]` | Approve a suggestion. | Admin o permiso Gestionar servidor |
| `!deny <reference> [reason]` | Deny a suggestion. | Admin o permiso Gestionar servidor |
| `!editsuggest <reference> <new_content>` | Edit your own suggestion (only if pending). | Todos |
| `!mysuggestions` | View your own suggestions. | Todos |
| `!setlogchannel <channel>` | [Legacy] Use [p]suggestset logchannel | Admin o permiso Administrator |
| `!setstatus <reference> <status> [reason]` | Change the status of a suggestion. | Admin o permiso Gestionar servidor |
| `!setsuggestionchannel <channel>` | [Legacy] Use [p]suggestset channel | Admin o permiso Administrator |
| `!suggest [suggestion]` | Submit a new suggestion. | Todos |
| `!suggestadmin purge [what=deleted]` | Permanently delete suggestions from the record. | Admin o permiso Administrator |
| `!suggestadmin repost <reference>` | Re-publish a deleted suggestion keeping its original ID. | Admin o permiso Administrator |
| `!suggestadmin resync` | Sync suggestions by verifying which messages still exist. Marks as deleted those suggestions whose message no longer exists. | Admin o permiso Administrator |
| `!suggestionhistory <reference>` | View the change history of a suggestion. | Admin o permiso Gestionar servidor |
| `!suggestioninfo <reference>` | View detailed information about a suggestion. | Todos |
| `!suggestions [status=all]` | List server suggestions. | Admin o permiso Gestionar servidor |
| `!suggestset autoarchive` | Enable/disable automatic thread archiving. | Admin o permiso Administrator |
| `!suggestset buttons` | Toggle between buttons and reactions. | Admin o permiso Administrator |
| `!suggestset channel <channel>` | Set the suggestion channel. | Admin o permiso Administrator |
| `!suggestset logchannel [channel]` | Set the log channel (or disable with no argument). | Admin o permiso Administrator |
| `!suggestset notify` | Enable/disable author notifications. | Admin o permiso Administrator |
| `!suggestset notifychannel [channel]` | Alternative channel for notifications (if DM fails). | Admin o permiso Administrator |
| `!suggestset settings` | Show the current configuration. | Admin o permiso Administrator |
| `!suggestset staffrole [role]` | Set the staff role that can manage suggestions. | Admin o permiso Administrator |
| `!suggestset threads` | Enable/disable automatic threads. | Admin o permiso Administrator |
| `!togglesuggestionthreads` | [Legacy] Use [p]suggestset threads | Admin o permiso Administrator |
| `!togglethreadarchive` | [Legacy] Use [p]suggestset autoarchive | Admin o permiso Administrator |
