# Tickets-Trini v3.0.0

Multi-panel support ticket system with buttons for Red-DiscordBot.

**Author**: [Killerbite95](https://github.com/killerbite95/killerbite-cogs)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎛️ **Multi-Panel** | Create multiple panels with different configurations |
| 🧵 **Threads or Channels** | Choose between private threads or text channels |
| 📝 **Modals/Forms** | Request information from users before opening a ticket |
| 📊 **Transcripts** | Automatically save conversation history |
| 🔔 **Notifications** | Configurable mentions and DMs |
| 🎨 **Full Customization** | Colors, emojis, text, and names |
| 👥 **Role System** | Global and per-panel support roles |
| ⏰ **Auto-close** | Automatically close inactive tickets |
| 📋 **Live Overview** | Panel showing all active tickets |
| 🚫 **Blacklist** | Block users or roles from opening tickets |
| 🌐 **Dashboard** | Web integration for Red-Dashboard |

---

## 📥 Installation

```
[p]repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
[p]cog install killerbite-cogs ticketstrini
[p]load ticketstrini
```

### Requirements
- Red-DiscordBot 3.5.0+
- Python 3.10+
- `numpy` and `chat-exporter` (installed automatically)

### Bot Permissions
- Manage Channels
- Manage Roles
- View Channel
- Send Messages
- Read Message History
- Embed Links
- Attach Files
- Create Private Threads (if using threads)
- Send Messages in Threads (if using threads)

---

## 🚀 Quick Setup

### 1. View Setup Guide
```
[p]tickets setuphelp
```

### 2. Add Support Role
```
[p]tickets supportrole @Staff
```
With auto-mention:
```
[p]tickets supportrole @Staff true
```

### 3. Create a Panel
```
[p]tickets addpanel support
```

### 4. Set Category
```
[p]tickets category support #TICKETS-CATEGORY
```

### 5. Set Panel Channel
```
[p]tickets channel support #open-ticket
```

### 6. Create Panel Embed
```
[p]tickets embed #5865F2 #open-ticket "🎫 Support Center" "Click the button below to open a ticket!"
```

### 7. Link Panel to Message
Get the message ID and run (in the same channel):
```
[p]tickets panelmessage support <message_id>
```

Done! The button should now appear.

---

## ⚙️ Configuration Commands

### Global Settings

| Command | Description |
|---------|-------------|
| `[p]tickets view` | View all settings |
| `[p]tickets maxtickets <num>` | Max tickets per user |
| `[p]tickets dm` | Toggle DM notifications |
| `[p]tickets transcript` | Toggle transcripts |
| `[p]tickets interactivetranscript` | Toggle HTML transcripts |
| `[p]tickets selfclose` | Toggle user self-close |
| `[p]tickets selfrename` | Toggle user self-rename |
| `[p]tickets selfmanage` | Toggle user adding others |
| `[p]tickets suspend [message]` | Suspend ticket system |

### Panel Configuration

| Command | Description |
|---------|-------------|
| `[p]tickets addpanel <name>` | Create new panel |
| `[p]tickets panels` | View/delete panels |
| `[p]tickets category <panel> <category>` | Set ticket category |
| `[p]tickets channel <panel> <channel>` | Set panel channel |
| `[p]tickets panelmessage <panel> <msg_id>` | Link to message |
| `[p]tickets logchannel <panel> <channel>` | Set log channel |
| `[p]tickets toggle <panel>` | Enable/disable panel |
| `[p]tickets usethreads <panel>` | Toggle thread mode |

### Button Customization

| Command | Description |
|---------|-------------|
| `[p]tickets buttontext <panel> <text>` | Set button text |
| `[p]tickets buttoncolor <panel> <color>` | Set color (red/blue/green/grey) |
| `[p]tickets buttonemoji <panel> <emoji>` | Set button emoji |
| `[p]tickets row <panel> <0-4>` | Set button row |
| `[p]tickets priority <panel> <num>` | Set button order |

### Roles

| Command | Description |
|---------|-------------|
| `[p]tickets supportrole <role> [mention]` | Add/remove global support role |
| `[p]tickets panelrole <panel> <role> [mention]` | Add/remove panel-specific role |
| `[p]tickets openrole <panel> <role>` | Require role to open ticket |
| `[p]tickets blacklist <user_or_role>` | Add/remove from blacklist |

### Modals (Forms)

| Command | Description |
|---------|-------------|
| `[p]tickets addmodal <panel> <field_name>` | Add/remove modal field |
| `[p]tickets viewmodal <panel>` | View modal fields |
| `[p]tickets modaltitle <panel> <title>` | Set modal title |
| `[p]tickets closemodal <panel>` | Toggle close reason modal |

### Messages

| Command | Description |
|---------|-------------|
| `[p]tickets addmessage <panel>` | Add ticket welcome message |
| `[p]tickets viewmessages <panel>` | View/delete messages |
| `[p]tickets embed <color> <channel> <title> <desc>` | Create embed |

### Advanced

| Command | Description |
|---------|-------------|
| `[p]tickets ticketname <panel> <format>` | Set channel name format |
| `[p]tickets noresponse <hours>` | Auto-close after X hours |
| `[p]tickets altchannel <panel> <channel>` | Set alternate channel |
| `[p]tickets autoadd` | Auto-add roles to threads |
| `[p]tickets maxclaims <panel> <num>` | Max staff per thread |
| `[p]tickets overview [channel]` | Set overview channel |
| `[p]tickets overviewmention` | Toggle channel mentions in overview |
| `[p]tickets threadclose` | Archive threads instead of delete |
| `[p]tickets cleanup` | Remove invalid tickets |
| `[p]tickets getlink <message>` | Get transcript link |

---

## 👤 User Commands

| Command | Description |
|---------|-------------|
| `[p]add <user>` | Add user to your ticket |
| `[p]renameticket <name>` | Rename your ticket |
| `[p]close [reason]` | Close your ticket |
| `[p]openfor <user> <panel>` | Open ticket for another user (Mod only) |

### Close Command Examples
```
[p]close                          # Close immediately
[p]close thanks for helping!      # Close with reason
[p]close 1h                       # Close in 1 hour
[p]close 1m thanks!               # Close in 1 minute with reason
```

---

## 📋 Ticket Name Variables

Use these in `[p]tickets ticketname`:

| Variable | Example |
|----------|---------|
| `{num}` | 42 |
| `{user}` | john |
| `{displayname}` | John Doe |
| `{id}` | 123456789 |
| `{shortdate}` | 12-25 |
| `{longdate}` | 12-25-2024 |
| `{time}` | 03-45-PM |

Example:
```
[p]tickets ticketname support ticket-{num}-{user}
# Result: ticket-42-john
```

---

## 📝 Message Variables

Use these in ticket messages:

| Variable | Result |
|----------|--------|
| `{username}` | Discord username |
| `{mention}` | @mention |
| `{id}` | User ID |

---

## 🎛️ Multi-Button Panels

Create multiple panels on the same message:

```
# Create panels
[p]tickets addpanel technical
[p]tickets addpanel sales
[p]tickets addpanel general

# Configure all with same channel/category
[p]tickets category technical #TICKETS
[p]tickets category sales #TICKETS
[p]tickets category general #TICKETS

[p]tickets channel technical #support
[p]tickets channel sales #support
[p]tickets channel general #support

# Link all to SAME message
[p]tickets panelmessage technical <message_id>
[p]tickets panelmessage sales <message_id>
[p]tickets panelmessage general <message_id>

# Customize buttons
[p]tickets buttontext technical "🛠️ Technical"
[p]tickets buttoncolor technical blue

[p]tickets buttontext sales "💰 Sales"
[p]tickets buttoncolor sales green

[p]tickets buttontext general "📋 General"
[p]tickets buttoncolor general grey

# Set order
[p]tickets priority technical 1
[p]tickets priority sales 2
[p]tickets priority general 3
```

---

## 🧵 Threads vs Channels

### Channels (Default)
- Creates a new text channel per ticket
- More visible in channel list
- Requires category management

### Threads
- Creates a private thread per ticket
- Lighter on server
- Better organization
- Enable with: `[p]tickets usethreads <panel>`

---

## 📊 Transcripts

### Enable Transcripts
```
[p]tickets transcript
```

### Interactive HTML Transcripts
```
[p]tickets interactivetranscript
```

Creates a visual HTML file that can be viewed in a browser.

---

## ⏰ Auto-Close

Close tickets automatically if user doesn't respond:

```
[p]tickets noresponse 24
```
Closes after 24 hours of inactivity.

```
[p]tickets noresponse 0
```
Disable auto-close.

For thread tickets, this uses Discord's archive settings:
- 1 hour
- 24 hours (1 day)
- 72 hours (3 days)
- 168 hours (1 week)

---

## 📋 Live Overview

Set up a channel showing all active tickets:

```
[p]tickets overview #tickets-overview
```

Toggle channel mentions:
```
[p]tickets overviewmention
```

---

## 🌐 Dashboard Integration

This cog includes Red-Dashboard integration for web-based ticket management.

---

## 🔧 Troubleshooting

### Buttons not appearing
1. Ensure category is set: `[p]tickets category <panel> <category>`
2. Ensure channel is set: `[p]tickets channel <panel> <channel>`
3. Ensure message is linked: `[p]tickets panelmessage <panel> <msg_id>`
4. Run `[p]tickets panels` to verify configuration

### Bot can't create tickets
- Check bot has "Manage Channels" permission
- Check bot has "Manage Roles" permission
- Check category permissions allow bot access

### Transcripts not working
- Ensure `chat-exporter` is installed
- Enable with `[p]tickets transcript`

### Clean up invalid tickets
```
[p]tickets cleanup
```

---

## 📚 Additional Resources

- [GUIA_COMPLETA.md](GUIA_COMPLETA.md) - Full guide in Spanish
- [README.md](README.md) - Command reference

---

## 📜 Version History

### v3.0.0 (Trini Edition)
- Renamed to tickets-trini
- Dashboard integration
- Multi-language support
- Bug fixes and improvements
