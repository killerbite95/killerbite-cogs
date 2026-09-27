# Day Counter

Cuenta los dias transcurridos desde una fecha.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs day_counter_cog
!load day_counter_cog
```

**Requisitos:** Ninguno.

## Puesta en marcha paso a paso

1. Fija la fecha de inicio (año, mes, dia): `!establecer_fecha 2025 1 15`.
2. Consulta cuantos dias han pasado: `!dias`.
3. Para empezar de cero: `!resetear_dias`.

Ahora mismo cualquier usuario puede cambiar o resetear la fecha. Si quieres limitarlo, usa el cog Permissions de Red (por ejemplo `!permissions addserverrule deny establecer_fecha @everyone`).

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!dias` | Muestra el número de días pasados desde la fecha de inicio. | Todos |
| `!establecer_fecha <year> <month> <day>` | Establece la fecha de inicio en formato año, mes, día. | Todos |
| `!resetear_dias` | Resetea la fecha de inicio. | Todos |
