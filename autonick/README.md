# AutoNick

Los usuarios escriben el apodo que quieren en un canal y el bot se lo pone automaticamente, con cooldown y lista de nombres prohibidos.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs autonick
!load autonick
```

**Requisitos:** El bot necesita **Manage Nicknames** y su rol por encima de los usuarios.

## Puesta en marcha paso a paso

1. Crea un canal para cambiar el apodo (por ejemplo `#cambiar-apodo`) y configuralo: `!autonick setchannel #cambiar-apodo`.
2. Ajusta el tiempo minimo entre cambios: `!autonick setcooldown 60` (segundos).
3. Añade palabras que no se permiten en los apodos: `!autonick admin addforbidden staff` (repite con cada una). Consultalas con `!autonick admin listforbidden`.
4. Revisa la configuracion: `!autonick info`.
5. Listo: cualquiera que escriba en ese canal recibe como apodo el texto de su mensaje.

Cada servidor tiene su propia lista de nombres prohibidos: empieza con la lista por defecto y los cambios que hagas solo afectan a ese servidor (tambien viaja con `!profile export`/`import`). Los apodos de mas de 32 caracteres se rechazan.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!autonick admin addforbidden <word>` | Añade una palabra o frase a la lista de nombres prohibidos. Ejemplo: `/autonick admin addforbidden [palabra o frase]` | Admin o permiso Gestionar servidor |
| `!autonick admin listforbidden` | Muestra la lista de todas las palabras o frases prohibidas. Ejemplo: `/autonick admin listforbidden` | Admin o permiso Gestionar servidor |
| `!autonick admin removeforbidden <word>` | Elimina una palabra o frase de la lista de nombres prohibidos. Ejemplo: `/autonick admin removeforbidden [palabra o frase]` | Admin o permiso Gestionar servidor |
| `!autonick info` | Muestra la configuración actual del cog AutoNick. Ejemplo: `/autonick info` | Todos |
| `!autonick setchannel <channel>` | Establece el canal donde se escucharán los mensajes para cambiar el apodo. Ejemplo: `/autonick setchannel #nombre-del-canal` | Admin o permiso Gestionar servidor |
| `!autonick setcooldown <seconds>` | Establece el cooldown (en segundos) entre cambios de apodo. Ejemplo: `/autonick setcooldown 30` | Admin o permiso Gestionar servidor |
