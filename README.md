# Killerbite Cogs

Collection of cogs for [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot) by **Killerbite95**.

## Installation

```
[p]repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
[p]cog install killerbite-cogs <cog_name>
[p]load <cog_name>
```

## Available Cogs

| Cog | Description |
|-----|-------------|
| **adv_check** | Advanced user verification system |
| **alienhost** | AlienHost (Pelican) integration: link your client API key via private modal and manage your servers, backups and alerts |
| **apiv2** | REST API server embedded in the bot for external integrations |
| **autonick** | Automatically manages user nicknames |
| **autoprune** | Borra automaticamente los creditos de los usuarios que siguen baneados |
| **blackjack** | Blackjack card game for Discord |
| **colacoins** | Virtual currency system with leaderboards |
| **day_counter_cog** | Counts days since/until events |
| **gameservermonitor** | Monitors game servers (CS2, Minecraft, DayZ, Valheim, ARK, TF2, L4D2, 7DTD, Palworld, etc.) with live embeds, slash commands, and interactive buttons |
| **listroles** | Lists server roles and their members |
| **maptrack** | Obsoleto: integrado en GameServerMonitor (`!gsmalerts`) |
| **suggestions** | Complete suggestion system with buttons, voting, and staff management |
| **ticketstrini** | Multi-panel support ticket system with buttons (Trini Edition) |
| **trinibackups** | Structural snapshots, diff, scheduled backups and safe (non-destructive) restore |
| **trinievents** | Community events with RSVP, waitlist, reminders, temp roles/channels, ArenCup and stats |
| **triniprofiles** | Profile-based setup for La Trini: modules, dependencies, presets and export/import |
| **trinisecurity** | Security audit, authority model, protected roles, anti-nuke, lockdown and incident reconstruction |
| **trickortreat** | Trick or Treat candy game with shop, streaks, events, and more |

## La Trini platform

`triniprofiles` → `trinisecurity` → `trinibackups` → `trinievents` → `alienhost` work together: Profiles prepares the server, Security audits and protects it, Backups stores comparable states (linked to Security incidents), Events drives community activity and AlienHost connects Discord with real infrastructure. **Step-by-step setup guide (Spanish): [docs/GUIA_LA_TRINI.md](docs/GUIA_LA_TRINI.md).** Roadmap: [docs/la_trini_roadmap_modulos.md](docs/la_trini_roadmap_modulos.md).

## Support

For issues or suggestions, open an issue on [GitHub](https://github.com/killerbite95/killerbite-cogs/issues).

## License

See [LICENSE](LICENSE) for details.