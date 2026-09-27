# Advanced Check

Verificacion completa de un usuario con interfaz interactiva: informacion basica, roles, fecha de entrada, avatar, permisos y actividad.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs adv_check
!load adv_check
```

**Requisitos:** Ninguno.

## Puesta en marcha paso a paso

1. Instala y carga el cog (ver arriba). No necesita configuracion.
2. Revisa a cualquier miembro: `!advcheck @usuario` (alias `!check`, o `/advcheck`).
3. Navega por la informacion con los botones del mensaje.

Solo pueden usarlo moderadores (Mod en Red) o superiores.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!advcheck <member>` | Realiza una verificación completa del usuario especificado. Alias: `check`. | Mod |
