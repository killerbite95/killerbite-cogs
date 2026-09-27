# Trick or Treat

Juego de Halloween: los usuarios piden caramelos, los comen, los roban, compran objetos en la tienda y participan en eventos del servidor.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs trickortreat
!load trickortreat
```

**Requisitos:** Para `!buycandy` hace falta el banco de Red. Solo administradores configuran.

## Puesta en marcha paso a paso

1. Añade el canal (o canales) donde se juega: `!totchannel add #halloween`.
2. Activa el juego en el servidor: `!tottoggle`.
3. (Opcional) Ajusta los tiempos: `!totcooldown 180` (entre partidas), `!totpickupcooldown 600`, `!totstealcooldown 600` y `!totshieldhours 4`.
4. Los jugadores escriben **`trick or treat`** en el canal para jugar. Tambien tienen `!pickup`, `!eatcandy`, `!stealcandy @usuario`, `!cinventory`, `!totshop` y `!cboard`.
5. (Opcional) Evento de servidor con objetivo comun: `!totevent start <tipo> <objetivo> 50`. Seguimiento con `!totevent status`.
6. Guia completa del juego: `!tothelp`.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!buycandy <pieces>` | Buy some candy with server currency. Prices could vary at any time. | Todos |
| `!cboard` | Show the candy eating leaderboard. | Todos |
| `!cinventory` | Check your candy bag — full inventory with stats! | Todos |
| `!eatcandy [number=1] [candy_type]` | Eat some candy. | Todos |
| `!pickup` | Pick up some candy, if there is any. | Todos |
| `!stealcandy [user]` | Steal some candy. Beware of shields! | Todos |
| `!totaddcandies <amount>` | Add candies to the guild pool. | Mod o permiso Administrator |
| `!totbalance` | [Admin] Check how many candies are 'on the ground' in the guild. | Mod o permiso Administrator |
| `!totbuy <item_name> [amount=1]` | Buy items from the Candy Shop. | Todos |
| `!totchannel add <channel>` | Add a text channel for Trick or Treating. | Mod o permiso Administrator |
| `!totchannel remove <channel>` | Remove a text channel from Trick or Treating. | Mod o permiso Administrator |
| `!totclearall [are_you_sure=False]` | [Owner] Clear all saved game data. | Owner del bot |
| `!totcooldown [cooldown_time=0]` | Set the cooldown time for trick or treating on the server. | Mod o permiso Administrator |
| `!totevent goal <amount>` | Change the goal for the current event. | Mod o permiso Administrator |
| `!totevent reward <amount>` | Change the reward for the current event. | Mod o permiso Administrator |
| `!totevent start <event_type> <goal> [reward=50]` | Start a guild event! | Mod o permiso Administrator |
| `!totevent status` | Check the current event progress. | Todos |
| `!totevent stop` | Stop the current guild event. | Mod o permiso Administrator |
| `!totgivecandy <user> <candy_type> <amount>` | [Admin] Add candy to a user's inventory. | Admin o permiso Administrator |
| `!tothelp` | 📖 Full game guide for Trick or Treat. | Todos |
| `!totpickupcooldown [seconds=0]` | Set the cooldown time for the pickup command (default: 600s). | Mod o permiso Administrator |
| `!totremovecandy <user> <candy_type> <amount>` | [Admin] Remove candy from a user's inventory. | Admin o permiso Administrator |
| `!totshieldhours [hours=0]` | Set how many hours a shield lasts (default: 4). | Mod o permiso Administrator |
| `!totshop` | Browse the Candy Shop! Spend candy on special items. | Todos |
| `!totstats [user]` | View detailed trick-or-treat statistics. | Todos |
| `!totstealcooldown [seconds=0]` | Set the cooldown time for the stealcandy command (default: 600s). | Mod o permiso Administrator |
| `!tottoggle` | Toggle trick or treating on the whole server. | Mod o permiso Administrator |
| `!totversion` | Trick or Treat version. | Todos |
