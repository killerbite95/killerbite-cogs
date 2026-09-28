# DayCounter

Contadores de dias desde una fecha (aniversario del servidor, dias online…) y **cuentas atras** hasta una fecha futura (eventos, torneos, wipes). Cada contador se muestra en un embed con los dias, un desglose en años, meses y dias, y una barra de progreso hasta el siguiente hito.

## Instalacion

```
!repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
!cog install killerbite-cogs day_counter_cog
!load day_counter_cog
```

## Puesta en marcha paso a paso

1. Crea un contador. Si la fecha es pasada cuenta dias; si es futura, es una cuenta atras:
   - `!dias crear principal 2023-01-15 Días de La Trini`
   - `!dias crear torneo 2026-12-20 Gran torneo de invierno`

   La fecha puede ir como `AAAA-MM-DD` o `DD/MM/AAAA`.
2. Consultalo: `!dias` (el principal) o `!dias torneo`. Todos a la vez: `!dias lista`.
3. (Opcional) Personaliza: `!dias editar torneo color #e67e22`, `!dias editar torneo emoji 🏆`, `!dias editar torneo descripcion Inscripciones abiertas en #torneos`.
4. (Opcional) Anuncia los hitos (7, 30, 100, 365, 500, 1000 dias, cada aniversario, y el dia de una cuenta atras) en un canal: `!dias hitos #anuncios`.
5. (Opcional) Canal contador, un canal (por ejemplo de voz) cuyo nombre muestra los dias y se actualiza solo: `!dias canal #dias principal 📅 Día {days}`. En el formato puedes usar `{days}`, `{weeks}`, `{months}` y `{years}`. Discord limita los cambios de nombre, asi que se actualiza como mucho una vez al dia.

Todo funciona tambien como `/dias`, y desde el dashboard (pagina **DayCounter → counters**, solo admins).

## Referencia completa de comandos

Prefijo `!` como ejemplo (alias `!days`). `<obligatorio>` · `[opcional]`.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!dias [nombre]` | Muestra un contador (el principal si no indicas nombre). En slash: `/dias ver`. | Todos |
| `!dias lista` | Todos los contadores del servidor. | Todos |
| `!dias crear <nombre> <fecha> [titulo]` | Crea o cambia la fecha de un contador. Fecha futura = cuenta atras. | Admin o permiso Gestionar servidor |
| `!dias editar <nombre> <campo> [valor]` | Campos: `titulo`, `descripcion`, `color` (#hex), `emoji`, `fecha`. Sin valor borra el campo. | Admin o permiso Gestionar servidor |
| `!dias borrar <nombre>` | Borra un contador. | Admin o permiso Gestionar servidor |
| `!dias hitos [canal]` | Canal para anunciar los hitos (sin canal lo desactiva). | Admin o permiso Gestionar servidor |
| `!dias canal [canal] [nombre] [formato]` | Canal que se renombra cada dia con el contador (sin canal lo desactiva). | Admin o permiso Gestionar servidor |

**Cambios respecto a la version 1:** la fecha que tuvieras se convierte automaticamente en el contador `principal`. `!establecer_fecha <año> <mes> <dia>` y `!resetear_dias` siguen funcionando (ocultos), pero ahora se usa `!dias crear` / `!dias borrar`.
