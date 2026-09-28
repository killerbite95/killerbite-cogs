# ColaCoins

Moneda virtual que gestionan los administradores, con clasificacion.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs colacoins
!load colacoins
```

**Requisitos:** Solo administradores para dar y quitar monedas.

## Puesta en marcha paso a paso

1. Elige el emoji de la moneda: `!setcolacoinemoji 🥤`.
2. Reparte monedas: `!givecolacoins @usuario 10` (y `!removecolacoins @usuario 5` para quitar).
3. Cada usuario ve las suyas con `!colacoins`.
4. Los administradores pueden consultar a cualquiera (`!checkcolacoins @usuario`) y ver la clasificacion (`!colacoinslist`).

Los saldos son **globales**: son los mismos en todos los servidores del bot. Mas detalle en [DOCUMENTATION.md](DOCUMENTATION.md).

## Dashboard

Pagina **colacoins**: clasificacion de los miembros del servidor y formulario para dar/quitar. Solo admins (los saldos son globales).

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!checkcolacoins <user>` | Check the ColaCoins amount of a user. Alias: `vercolacoins`, `viewcolacoins`. | Admin o permiso Administrator |
| `!colacoins` | See how many ColaCoins you have. Alias: `mycolacoins`, `miscolacoins`. | Todos |
| `!colacoinslist` | Shows a leaderboard of users with the most ColaCoins. Alias: `colacoinslista`. | Admin o permiso Administrator |
| `!givecolacoins <user> <amount>` | Give ColaCoins to a user. Alias: `darcolacoins`. | Admin o permiso Administrator |
| `!removecolacoins <user> <amount>` | Remove ColaCoins from a user. Alias: `quitarcolacoins`. | Admin o permiso Administrator |
| `!setcolacoinemoji <emoji>` | Set the emoji for ColaCoins. Alias: `establecercolacoinemoji`. | Admin o permiso Administrator |
