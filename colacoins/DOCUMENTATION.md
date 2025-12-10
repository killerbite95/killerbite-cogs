# ColaCoins - Documentation / Documentación

**Version:** 1.0.0  
**Author:** Killerbite95  
**Compatible with:** Red-DiscordBot 3.5.22+

---

## 🇬🇧 English

### Description

**ColaCoins** is a virtual currency cog for Red Discord Bot. It allows server administrators to manage a custom currency system called "ColaCoins" that can be given to or removed from users. Users can check their own balance, and administrators can view leaderboards and manage the currency across the server.

### Features

- ✅ Give ColaCoins to users (admin)
- ✅ Remove ColaCoins from users (admin)
- ✅ Check any user's balance (admin)
- ✅ Check your own balance (everyone)
- ✅ Customizable emoji for currency display
- ✅ Leaderboard with pagination
- ✅ Bilingual support (English/Spanish via command aliases)
- ✅ Persistent data storage

---

### Commands

#### Admin Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `[p]givecolacoins <user> <amount>` | `darcolacoins` | Give ColaCoins to a user |
| `[p]removecolacoins <user> <amount>` | `quitarcolacoins` | Remove ColaCoins from a user |
| `[p]vercolacoins <user>` | `viewcolacoins` | Check a user's ColaCoins balance |
| `[p]setcolacoinemoji <emoji>` | `establecercolacoinemoji` | Set the emoji displayed with ColaCoins |
| `[p]colacoinslist` | - | Show leaderboard (English) |
| `[p]colacoinslista` | - | Show leaderboard (Spanish) |

#### User Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `[p]colacoins` | `miscolacoins` | Check your own ColaCoins balance |

---

### Usage Examples

```
# Give 100 ColaCoins to a user
[p]givecolacoins @User 100
[p]darcolacoins @User 100

# Remove 50 ColaCoins from a user
[p]removecolacoins @User 50
[p]quitarcolacoins @User 50

# Check a user's balance (admin)
[p]vercolacoins @User
[p]viewcolacoins @User

# Check your own balance
[p]colacoins
[p]miscolacoins

# Set custom emoji
[p]setcolacoinemoji 🪙
[p]setcolacoinemoji <:customcoin:123456789>

# View leaderboard
[p]colacoinslist
[p]colacoinslista
```

---

### Data Storage

The cog uses two storage mechanisms:
1. **Red's Config system** - Primary storage using `Config.get_conf()`
2. **JSON file backup** - Secondary backup to `colacoins_data.json`

#### Data Structure

```json
{
    "colacoins": {
        "user_id": amount
    },
    "emoji": "🪙"
}
```

---

### Leaderboard Features

- 🥇🥈🥉 Medal icons for top 3 positions
- Pagination with 10 users per page
- Navigation via reaction buttons (◀️ ▶️)
- 2-minute timeout for pagination
- Shows total user count in footer

---

### Permissions

| Permission Level | Commands |
|-----------------|----------|
| Administrator | `givecolacoins`, `removecolacoins`, `vercolacoins`, `setcolacoinemoji`, `colacoinslist`, `colacoinslista` |
| Everyone | `colacoins`, `miscolacoins` |

---

### Logging

The cog logs the following events:
- ColaCoins given to users
- ColaCoins removed from users
- Balance checks
- Emoji configuration changes
- Data load/save operations

---

## 🇪🇸 Español

### Descripción

**ColaCoins** es un cog de moneda virtual para Red Discord Bot. Permite a los administradores del servidor gestionar un sistema de moneda personalizado llamado "ColaCoins" que puede ser dado o quitado a los usuarios. Los usuarios pueden verificar su propio saldo, y los administradores pueden ver leaderboards y gestionar la moneda en todo el servidor.

### Características

- ✅ Dar ColaCoins a usuarios (admin)
- ✅ Quitar ColaCoins a usuarios (admin)
- ✅ Verificar saldo de cualquier usuario (admin)
- ✅ Verificar tu propio saldo (todos)
- ✅ Emoji personalizable para mostrar la moneda
- ✅ Leaderboard con paginación
- ✅ Soporte bilingüe (Inglés/Español mediante aliases)
- ✅ Almacenamiento persistente de datos

---

### Comandos

#### Comandos de Administrador

| Comando | Alias | Descripción |
|---------|-------|-------------|
| `[p]darcolacoins <usuario> <cantidad>` | `givecolacoins` | Da ColaCoins a un usuario |
| `[p]quitarcolacoins <usuario> <cantidad>` | `removecolacoins` | Quita ColaCoins a un usuario |
| `[p]vercolacoins <usuario>` | `viewcolacoins` | Verifica el saldo de ColaCoins de un usuario |
| `[p]establecercolacoinemoji <emoji>` | `setcolacoinemoji` | Establece el emoji mostrado con las ColaCoins |
| `[p]colacoinslista` | - | Muestra el leaderboard (Español) |
| `[p]colacoinslist` | - | Muestra el leaderboard (Inglés) |

#### Comandos de Usuario

| Comando | Alias | Descripción |
|---------|-------|-------------|
| `[p]miscolacoins` | `colacoins` | Verifica tu propio saldo de ColaCoins |

---

### Ejemplos de Uso

```
# Dar 100 ColaCoins a un usuario
[p]darcolacoins @Usuario 100
[p]givecolacoins @Usuario 100

# Quitar 50 ColaCoins a un usuario
[p]quitarcolacoins @Usuario 50
[p]removecolacoins @Usuario 50

# Verificar el saldo de un usuario (admin)
[p]vercolacoins @Usuario
[p]viewcolacoins @Usuario

# Verificar tu propio saldo
[p]miscolacoins
[p]colacoins

# Establecer emoji personalizado
[p]establecercolacoinemoji 🪙
[p]establecercolacoinemoji <:moneda:123456789>

# Ver leaderboard
[p]colacoinslista
[p]colacoinslist
```

---

### Almacenamiento de Datos

El cog usa dos mecanismos de almacenamiento:
1. **Sistema Config de Red** - Almacenamiento principal usando `Config.get_conf()`
2. **Respaldo en archivo JSON** - Respaldo secundario en `colacoins_data.json`

#### Estructura de Datos

```json
{
    "colacoins": {
        "id_usuario": cantidad
    },
    "emoji": "🪙"
}
```

---

### Características del Leaderboard

- 🥇🥈🥉 Iconos de medalla para los 3 primeros puestos
- Paginación con 10 usuarios por página
- Navegación mediante botones de reacción (◀️ ▶️)
- Timeout de 2 minutos para la paginación
- Muestra el total de usuarios en el pie de página

---

### Permisos

| Nivel de Permiso | Comandos |
|-----------------|----------|
| Administrador | `darcolacoins`, `quitarcolacoins`, `vercolacoins`, `establecercolacoinemoji`, `colacoinslista`, `colacoinslist` |
| Todos | `miscolacoins`, `colacoins` |

---

### Registro (Logging)

El cog registra los siguientes eventos:
- ColaCoins dadas a usuarios
- ColaCoins quitadas a usuarios
- Verificaciones de saldo
- Cambios de configuración de emoji
- Operaciones de carga/guardado de datos

---

## Technical Details / Detalles Técnicos

### File Structure

```
colacoins/
├── __init__.py          # Cog loader
├── colacoins.py         # Main cog code
├── info.json            # Cog metadata
└── DOCUMENTATION.md     # This file
```

### Dependencies

- `discord.py` (included with Red)
- `redbot.core` (Red-DiscordBot framework)
- `asyncio` (Python standard library)
- `json` (Python standard library)
- `os` (Python standard library)
- `logging` (Python standard library)

### Configuration Identifier

```python
Config.get_conf(self, identifier=1234567890, force_registration=True)
```

### Current Limitations

1. Data is stored globally, not per-guild
2. JSON backup file location is hardcoded
3. No transaction history
4. No transfer command between users
5. Uses legacy reaction-based pagination instead of Discord buttons
6. Duplicate code for bilingual messages
7. No rate limiting on commands
8. `on_ready` event for data loading (not recommended)

---

## Changelog

### v1.0.0
- Initial release
- Basic give/remove/check commands
- Leaderboard with pagination
- Custom emoji support
- Bilingual support (EN/ES)
