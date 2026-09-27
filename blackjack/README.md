# Blackjack

Blackjack con botones (Hit, Stand, Double Down, Split) apostando creditos del banco de Red.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs blackjack
!load blackjack
```

**Requisitos:** Economia/banco de Red activo (`!bank` / cog Economy).

## Puesta en marcha paso a paso

1. Asegurate de que el banco de Red funciona y los jugadores tienen creditos (`!bank balance`).
2. Juega una mano: `!blackjack 100` (apuesta 100 creditos). Usa los botones del mensaje para jugar.
3. (Opcional) Personaliza las cartas con emojis: `!bjadmin setrank A <emoji>`, `!bjadmin setsuit hearts <emoji>`. Revisalo con `!bjadmin show` y vuelve a los de serie con `!bjadmin reset`.

Tal como esta programado, `!blackjack` solo lo pueden usar moderadores o quien tenga Gestionar servidor. La configuracion de emojis es comun a todo el bot.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!blackjack <bet>` | Juega una mano de Blackjack apostando creditos del banco de Red. | Mod o permiso Gestionar servidor |
| `!bjadmin setrank <rank> <emoji>` | Cambia el emoji de un valor de carta (A, 2-10, J, Q, K). | Admin o permiso Administrator |
| `!bjadmin setsuit <suit> <emoji>` | Cambia el emoji de un palo. | Admin o permiso Administrator |
| `!bjadmin show` | Muestra la configuracion de emojis. | Admin o permiso Administrator |
| `!bjadmin reset` | Restablece los emojis por defecto. | Admin o permiso Administrator |
