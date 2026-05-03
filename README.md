# Hermes Language Labyrinth

A language-learning RPG skill for [hermes-agent](https://github.com/NousResearch/hermes-agent). The agent becomes an immersive Dungeon Master that narrates entirely in your target language, silently corrects your errors by modelling correct usage, and logs vocabulary as it goes.

---

## What It Does

- **Immersive narration** — the DM writes 100–150 words per turn in your target language
- **Silent error correction** — grammar mistakes are corrected by example, never by comment
- **Vocabulary logging** — new, misused, and rare words are logged automatically per session
- **Resumable sessions** — every turn is saved to disk; you can quit mid-session and resume
- **CEFR-aware language** — narration complexity matches A1 through C2 levels
- **Story pacing** — the DM advances the plot every turn and introduces complications if needed

---

## Prerequisites

- [hermes-agent](https://github.com/NousResearch/hermes-agent) v0.12.0 or later (`~/.local/bin/hermes`)
- Python 3.10+ (for `main.py` — stdlib only, no extra packages needed)
- An OpenRouter API key (or any OpenAI-compatible provider)

---

## Quick Start

```/dev/null/quickstart.sh#L1-8
# 1. Clone the repo (if you haven't already)
git clone <repo-url> hermes-language-labyrinth
cd hermes-language-labyrinth

# 2. Run the installer
bash install.sh

# 3. Add your API key (if not already in ~/.hermes/.env)
echo 'OPENROUTER_API_KEY=sk-or-...' >> ~/.hermes/.env

# 4. Create a campaign
python main.py create

# 5. Start playing
python main.py play
```

---

## File Layout

```/dev/null/layout.txt#L1-12
hermes-language-labyrinth/
├── skills/
│   └── language-labyrinth/
│       └── SKILL.md           # DM rulebook (source; installed by install.sh)
├── tools/
│   └── labyrinth_tools.py     # Tool handlers + schemas (symlinked into plugin)
├── config/
│   ├── SOUL.md                # DM persona (installed to ~/.hermes/SOUL.md)
│   ├── CAMPAIGN.md.template   # Session context template
│   └── config_reference.yaml  # Config snippets to merge into ~/.hermes/config.yaml
├── main.py                    # Campaign launcher CLI
└── install.sh                 # One-shot deployment script
```

**Installed to `~/.hermes`:**

| Source | Destination | Purpose |
|---|---|---|
| `tools/labyrinth_tools.py` | `~/.hermes/plugins/labyrinth/tools.py` (symlink) | Tool handlers |
| `~/.hermes/plugins/labyrinth/__init__.py` | (written by install.sh) | Plugin registration |
| `skills/language-labyrinth/SKILL.md` | `~/.hermes/skills/gaming/language-labyrinth/SKILL.md` | DM rulebook |
| `config/SOUL.md` | `~/.hermes/SOUL.md` | DM persona |
| — | `~/.hermes/labyrinth/` | Campaign data directory |

---

## The Three Custom Tools

| Tool | Emoji | When called |
|---|---|---|
| `get_story_context` | 🗺️ | Once at session start — loads act, session number, story summary |
| `log_vocabulary` | 📚 | During narration — buffers new/misused/rare words |
| `save_turn` | 💾 | End of every turn — writes turn + vocab to campaign JSON |

All three belong to the `labyrinth` toolset. The DM never sees a default terminal, browser, or file tool — only `labyrinth`, `skills`, and `memory` are active during a session.

---

## Campaign Management (`main.py`)

```/dev/null/main-help.txt#L1-18
python main.py create                   # Interactive wizard — new campaign
python main.py list                     # List all campaigns
python main.py play                     # Start/resume current campaign
python main.py play --campaign <id>     # Start/resume a specific campaign
python main.py use <campaign-id>        # Switch active campaign
python main.py summary                  # Learning summary for current campaign
python main.py summary --campaign <id>  # Learning summary for a specific campaign
```

### Campaign data

Each campaign is stored as a single JSON file:

```/dev/null/example-campaign.json#L1-20
~/.hermes/labyrinth/<uuid>/campaign.json
{
  "campaign_id": "...",
  "player_name": "Aria",
  "player_class": "Scholar",
  "target_language": "Spanish",
  "native_language": "English",
  "language_level": "B1",
  "current_session": 3,
  "total_sessions": 10,
  "session_target_minutes": 30.0,
  "act_name": "The Dark Market",
  "story_summary": "Aria found the stolen manuscript...",
  "acts": [...],
  "turns": [...],
  "vocabulary": [...]
}
```

The active campaign is tracked by `~/.hermes/labyrinth/current` (a file containing the path to the active `campaign.json`).

---

## Configuration

### Recommended model

The spec recommends `moonshotai/kimi-k2` via OpenRouter. Change your model with:

```/dev/null/model-change.sh#L1-2
hermes model set moonshotai/kimi-k2 --provider openrouter
```

Or merge `config/config_reference.yaml` into `~/.hermes/config.yaml`.

### Toolset restriction

`main.py play` launches hermes with `-t labyrinth,skills,memory` so the DM only ever sees the three labyrinth tools plus memory. You can make this the CLI default by editing `~/.hermes/config.yaml`:

```/dev/null/config-snippet.yaml#L1-7
agent:
  disabled_toolsets:
    - terminal
    - browser
    - web
    - file
    - vision
```

### SOUL.md

`install.sh` copies `config/SOUL.md` to `~/.hermes/SOUL.md`, replacing (with backup) any existing file. If you already have a custom SOUL.md you want to keep, merge the DM persona manually.

---

## Spec Deviations (and Why)

| Spec | Actual | Reason |
|---|---|---|
| `SOUL.md` → `~/.hermes/memories/SOUL.md` | `~/.hermes/SOUL.md` | Correct path in hermes v0.12 |
| `CAMPAIGN.md` → `~/.hermes/context/CAMPAIGN.md` (auto-loaded) | `main.py` renders template to `.hermes.md` in project CWD | No `context/` auto-load exists; `.hermes.md` IS auto-loaded |
| `toolsets: {enabled: [labyrinth], disabled: [...]}` in config.yaml | Plugin enabled via `plugins.enabled`; toolsets restricted via `-t` flag | Actual config key is `plugins.enabled`; per-session toolsets via `-t` |
| Custom tools placed in project `tools/` only | Symlinked into `~/.hermes/plugins/labyrinth/` | hermes discovers tools only from registered plugins |
| `api_key:` in config.yaml | API keys in `~/.hermes/.env` only | hermes security policy — keys never in config.yaml |

---

## Development

Edits to `tools/labyrinth_tools.py` are immediately live — the plugin's `tools.py` is a symlink to the repo file. Restart hermes to pick up changes.

```/dev/null/dev.sh#L1-6
# Verify tools are registered
hermes tools list | grep -E "log_vocabulary|save_turn|get_story_context"

# Check plugin status
hermes plugins list | grep labyrinth

# Run a dry-run install (no writes)
bash install.sh --dry-run
```

---

## License

MIT
