# AutoPrune (PruneBans)

Borra automaticamente los creditos del banco de Red de los usuarios que **siguen baneados** pasados unos dias. No publica nada al banear o desbanear: de eso ya se encarga el modlog. Solo deja un resumen en el canal de logs cuando borra creditos.

## Instalacion

```
!repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
!cog install killerbite-cogs autoprune
!load autoprune
```

## Requisitos

- El bot necesita **Banear miembros** para ver la lista de baneos: antes de borrar comprueba que el usuario sigue baneado.
- Usa el banco de Red (`!bank`).

## Puesta en marcha paso a paso

1. Activalo: `!autoprune enable`.
2. (Opcional) Cambia la espera, por defecto 7 dias: `!autoprune days 14`.
3. (Opcional) Canal donde avisar cuando se borran creditos: `!autoprune logchannel #logs-economia`.
4. (Opcional) Si ya habia gente baneada, añadela al seguimiento (su cuenta atras empieza hoy): `!autoprune sync`.
5. Comprueba el estado con `!autoprune` y los pendientes con `!autoprune pending`.

A partir de ahi es automatico. Cada hora el bot revisa los baneos vencidos:

- Si sigue baneado, borra su cuenta del banco en este servidor y lo avisa en el canal de logs.
- Si lo desbanearon antes, deja de seguirlo y no toca nada.

**Banco global:** con banco global la cuenta es la misma en todos los servidores, y un ban en uno le quitaria los creditos en todos. Por eso, en ese caso no se borra nada hasta que el owner lo permita con `!autoprune globalbank true`. Mientras, el seguimiento se conserva.

> Tambien desde el dashboard: pagina **PruneBans → bans** (los mods la ven y solo los admins la cambian).

## Referencia completa de comandos

Prefijo `!` como ejemplo (alias `!prunebans`). `<obligatorio>` · `[opcional]`. Tambien funciona como `/autoprune`.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!autoprune` | Estado: activado, dias de espera, canal de logs, pendientes y tipo de banco. | Admin o permiso Gestionar servidor |
| `!autoprune enable` / `disable` | Activar o desactivar la limpieza automatica en este servidor. | Admin o permiso Gestionar servidor |
| `!autoprune days <0-365>` | Dias que debe seguir baneado antes de borrar sus creditos. Se recalcula para los pendientes. | Admin o permiso Gestionar servidor |
| `!autoprune logchannel [canal]` | Canal donde avisar al borrar creditos (sin canal lo quita). | Admin o permiso Gestionar servidor |
| `!autoprune pending` | Baneos en seguimiento, creditos y cuando se limpiaran. | Admin o permiso Gestionar servidor |
| `!autoprune sync` | Añadir al seguimiento a los que ya estaban baneados. | Admin o permiso Gestionar servidor |
| `!autoprune run [true]` | Revisar ya los vencidos; con `true` limpia todos los pendientes sin esperar. | Admin o permiso Gestionar servidor |
| `!autoprune forget <user_id>` | Dejar de seguir a un usuario (no se le borran los creditos). | Admin o permiso Gestionar servidor |
| `!autoprune globalbank <true/false>` | Permitir borrar cuentas del banco global. | Owner del bot |

## Cambios respecto a la version 1

Ya no existen `!prune`, `!prunetest`, `!listbans`, `!countdown`, `!setbanlog` ni `!setlogprune`. Si tenias configurado el canal de bans, al actualizar la limpieza queda **activada** y ese canal pasa a ser el de logs. Puedes cambiarlo con `!autoprune logchannel`.
