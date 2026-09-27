# AutoPrune (PruneBans)

Controla a los usuarios baneados y sus creditos del banco de Red: registra cada ban con su saldo, cuenta 7 dias y permite hacer prune de las cuentas de banco de los baneados.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs autoprune
!load autoprune
```

**Requisitos:** Economia/banco de Red activo. Solo administradores.

## Puesta en marcha paso a paso

1. Canal donde se registran los bans y la cuenta atras: `!setbanlog #logs-bans`.
2. Canal donde se registran los prunes: `!setlogprune #logs-prune`.
3. A partir de ahora, cada ban se registra solo con el saldo del usuario. Si se desbanea, sale del registro.
4. Consulta el estado: `!listbans` (baneados y sus creditos) y `!countdown` (cuenta atras de 7 dias). Cada dia el bot avisa en el canal de bans de quien ya ha cumplido los 7 dias.
5. Antes de hacer prune, mira a quien afectaria: `!prunetest`.
6. Ejecuta el prune (pide confirmacion): `!prune`.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!countdown` | Show a custom 7-day countdown for each ban. | Admin o permiso Administrator |
| `!listbans` | List banned users with their credits. | Admin o permiso Administrator |
| `!prune` | Execute prune manually after confirmation. | Admin o permiso Administrator |
| `!prunetest` | Test command to show users that would be affected by prune. | Admin o permiso Administrator |
| `!setbanlog <channel>` | Set the channel where ban logs will be sent. | Admin o permiso Administrator |
| `!setlogprune <channel>` | Set the channel where prune logs will be sent. | Admin o permiso Administrator |
