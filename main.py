#!/usr/bin/env python3
"""
main.py — Hermes Language Labyrinth campaign launcher.

Subcommands
-----------
  create   Interactive wizard to create a new campaign.
  list     List all campaigns under the data directory.
  play     Render campaign context and launch a hermes session.
  summary  Print learning progress for a campaign.
  use      Set a campaign as the current active campaign.

Environment
-----------
  LABYRINTH_DATA_DIR   Override the default ~/.hermes/labyrinth/ data directory.
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

# Absolute path of this script's directory (the project root).
SCRIPT_DIR = Path(__file__).parent.resolve()

# Campaign data directory — overridable via environment variable.
DATA_DIR = Path(
    os.environ.get("LABYRINTH_DATA_DIR", Path.home() / ".hermes" / "labyrinth")
)

# Pointer file that holds the path of the active campaign.json.
CURRENT_FILE = DATA_DIR / "current"

# Jinja-less template (uses str.format placeholders).
TEMPLATE_PATH = SCRIPT_DIR / "config" / "CAMPAIGN.md.template"

# Context file that hermes reads from the project directory.
HERMES_MD = SCRIPT_DIR / ".hermes.md"

# hermes binary location.
HERMES_BIN = str(Path.home() / ".local" / "bin" / "hermes")


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def ensure_data_dir() -> None:
    """Create the labyrinth data directory (and parents) if absent."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def prompt(message: str, default: str = "") -> str:
    """
    Prompt the user for a line of text.
    Pressing Enter without typing returns *default* when one is provided.
    """
    if default:
        answer = input(f"{message} [{default}]: ").strip()
        return answer if answer else default
    return input(f"{message}: ").strip()


def load_campaign(campaign_json_path: Path) -> dict:
    """Load and return a campaign dict; exit with an error on failure."""
    if not campaign_json_path.exists():
        print(f"Error: Campaign file not found: {campaign_json_path}", file=sys.stderr)
        sys.exit(1)
    try:
        with campaign_json_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"Error: Could not parse {campaign_json_path}: {exc}", file=sys.stderr)
        sys.exit(1)


def save_campaign(campaign: dict, campaign_json_path: Path) -> None:
    """Serialise a campaign dict back to its JSON file (pretty-printed)."""
    with campaign_json_path.open("w", encoding="utf-8") as fh:
        json.dump(campaign, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def set_current_campaign(campaign_json_path: Path) -> None:
    """Write the campaign JSON path into the 'current' pointer file."""
    ensure_data_dir()
    CURRENT_FILE.write_text(str(campaign_json_path), encoding="utf-8")


def get_current_campaign_path() -> Path | None:
    """Return the Path stored in the 'current' pointer file, or None if absent."""
    if not CURRENT_FILE.exists():
        return None
    raw = CURRENT_FILE.read_text(encoding="utf-8").strip()
    return Path(raw) if raw else None


def resolve_campaign_path(campaign_id: str | None) -> Path:
    """
    Return the campaign.json Path for *campaign_id*.

    If *campaign_id* is None, fall back to the current-campaign pointer.
    Exits with a clear error when neither is available or the file is missing.
    """
    if campaign_id:
        path = DATA_DIR / campaign_id / "campaign.json"
        if not path.exists():
            print(f"Error: No campaign found with id '{campaign_id}'.", file=sys.stderr)
            sys.exit(1)
        return path

    # No explicit id — try the current pointer.
    current = get_current_campaign_path()
    if current is None:
        print(
            "No active campaign set.\n"
            "  Run `python main.py create`        to start a new campaign.\n"
            "  Run `python main.py use <id>`      to activate an existing one.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not current.exists():
        print(
            f"Error: Active campaign file is missing: {current}\n"
            "Run `python main.py use <campaign_id>` to point to a valid campaign.",
            file=sys.stderr,
        )
        sys.exit(1)
    return current


def iter_campaigns():
    """Yield (campaign_id_str, campaign_json_Path) for every campaign found."""
    if not DATA_DIR.exists():
        return
    for entry in sorted(DATA_DIR.iterdir()):
        if entry.is_dir():
            json_path = entry / "campaign.json"
            if json_path.exists():
                yield entry.name, json_path


def to_bullet_list(items: list[str]) -> str:
    """Convert a list of strings into a Markdown unordered list."""
    if not items:
        return "- *(none)*"
    return "\n".join(f"- {item}" for item in items)


def render_template(campaign: dict) -> str:
    """
    Read CAMPAIGN.md.template, substitute all campaign fields, and return the
    full string (with a top-level header prepended).
    """
    if not TEMPLATE_PATH.exists():
        print(f"Error: Template not found at {TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Locate the current act; fall back to the first act in the list.
    act_name = campaign.get("act_name", "")
    acts = campaign.get("acts", [])
    current_act = next(
        (a for a in acts if a.get("name") == act_name), acts[0] if acts else {}
    )

    rendered = template.format(
        player_name=campaign.get("player_name", ""),
        player_class=campaign.get("player_class", ""),
        target_language=campaign.get("target_language", ""),
        native_language=campaign.get("native_language", ""),
        language_level=campaign.get("language_level", ""),
        current_session=campaign.get("current_session", 1),
        total_sessions=campaign.get("total_sessions", 10),
        session_target_minutes=campaign.get("session_target_minutes", 30.0),
        act_name=act_name,
        story_summary=campaign.get("story_summary", ""),
        act_narrative_goals=to_bullet_list(current_act.get("narrative_goals", [])),
        act_suggested_beats=to_bullet_list(current_act.get("suggested_beats", [])),
    )

    # Hermes expects this header as the first line of the context file.
    header = "# Language Labyrinth — Campaign Context\n\n"
    return header + rendered


def count_turns_for_session(campaign: dict, session_num: int) -> int:
    """Return the number of turns that belong to *session_num*."""
    return sum(
        1 for turn in campaign.get("turns", []) if turn.get("session") == session_num
    )


# ---------------------------------------------------------------------------
# Subcommand: create
# ---------------------------------------------------------------------------


def cmd_create(args: argparse.Namespace) -> None:
    """Interactive wizard to create and register a new campaign."""
    ensure_data_dir()

    print("=== New Language Labyrinth Campaign ===\n")

    player_name = prompt("Player name", "Adventurer")
    player_class = prompt("Player class", "Explorer")
    target_language = prompt("Target language", "Spanish")
    native_language = prompt("Native language", "English")

    # Validate language level against the CEFR scale.
    valid_levels = ["A1", "A2", "B1", "B2", "C1", "C2"]
    while True:
        raw_level = prompt("Language level [A1/A2/B1/B2/C1/C2]", "B1").upper()
        if raw_level in valid_levels:
            language_level = raw_level
            break
        print(f"  Please enter one of: {', '.join(valid_levels)}")

    while True:
        try:
            total_sessions = int(prompt("Number of sessions", "10"))
            break
        except ValueError:
            print("  Please enter a whole number.")

    while True:
        try:
            session_target_minutes = float(prompt("Session length in minutes", "30"))
            break
        except ValueError:
            print("  Please enter a number.")

    act_name = prompt("First act name", "The Beginning")

    print("\nNarrative goals for the first act (comma-separated, or leave blank):")
    goals_raw = input("> ").strip()
    narrative_goals = (
        [g.strip() for g in goals_raw.split(",") if g.strip()] if goals_raw else []
    )

    print("Story beats for the first act (comma-separated, or leave blank):")
    beats_raw = input("> ").strip()
    suggested_beats = (
        [b.strip() for b in beats_raw.split(",") if b.strip()] if beats_raw else []
    )

    campaign_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    campaign: dict = {
        "campaign_id": campaign_id,
        "player_name": player_name,
        "player_class": player_class,
        "target_language": target_language,
        "native_language": native_language,
        "language_level": language_level,
        "current_session": 1,
        "total_sessions": total_sessions,
        "session_target_minutes": session_target_minutes,
        "act_name": act_name,
        "story_summary": "",
        "created_at": created_at,
        "acts": [
            {
                "name": act_name,
                "narrative_goals": narrative_goals,
                "suggested_beats": suggested_beats,
            }
        ],
        "turns": [],
        "vocabulary": [],
    }

    # Persist campaign to disk.
    campaign_dir = DATA_DIR / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    campaign_json_path = campaign_dir / "campaign.json"
    save_campaign(campaign, campaign_json_path)

    # Activate this campaign as the current one.
    set_current_campaign(campaign_json_path)

    print(f"\n  Campaign ID : {campaign_id}")
    print(f"  Player      : {player_name} ({player_class})")
    print(
        f"  Language    : {target_language} ({language_level}), native {native_language}"
    )
    print(f"  Sessions    : {total_sessions} x {session_target_minutes} min")
    print(f"  First act   : {act_name}")
    print("\nCampaign set as current. Run `python main.py play` to begin!")


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> None:
    """Print a table of all campaigns, marking the active one with '*'."""
    current_path = get_current_campaign_path()

    campaigns = list(iter_campaigns())
    if not campaigns:
        print("No campaigns found. Run `python main.py create` to start one.")
        return

    # Fixed column widths for a tidy table.
    id_w, name_w, lang_w, level_w = 36, 14, 14, 7
    header = (
        f"  {'CAMPAIGN ID':<{id_w}}  "
        f"{'PLAYER':<{name_w}}  "
        f"{'LANGUAGE':<{lang_w}}  "
        f"{'LEVEL':<{level_w}}  "
        f"SESSION"
    )
    print(header)
    print("-" * len(header))

    for cid, cpath in campaigns:
        try:
            c = load_campaign(cpath)
        except SystemExit:
            print(f"  {cid}  (could not read campaign.json)")
            continue

        # Mark the active campaign with an asterisk.
        is_current = bool(current_path and cpath.resolve() == current_path.resolve())
        marker = "* " if is_current else "  "

        session_str = f"{c.get('current_session', '?')}/{c.get('total_sessions', '?')}"
        print(
            f"{marker}"
            f"{c.get('campaign_id', cid):<{id_w}}  "
            f"{c.get('player_name', '?'):<{name_w}}  "
            f"{c.get('target_language', '?'):<{lang_w}}  "
            f"{c.get('language_level', '?'):<{level_w}}  "
            f"{session_str}"
        )

    print("\n* = active campaign")


# ---------------------------------------------------------------------------
# Subcommand: play
# ---------------------------------------------------------------------------


def cmd_play(args: argparse.Namespace) -> None:
    """
    Prepare the session context file and hand off to the hermes agent.

    Session increment rule
    ----------------------
    - If *current_session* already has >= 1 turn logged, the player finished
      that session, so we bump the counter before launching.
    - If *current_session* has 0 turns (mid-session resume or brand new), we
      leave the counter alone.
    """
    campaign_json_path = resolve_campaign_path(getattr(args, "campaign", None))
    campaign = load_campaign(campaign_json_path)

    # --- Determine whether to start a new session or resume the current one ---
    current_session: int = campaign.get("current_session", 1)
    turns_this_session = count_turns_for_session(campaign, current_session)

    if turns_this_session > 0:
        new_session = current_session + 1
        print(
            f"Session {current_session} has {turns_this_session} recorded turn(s). "
            f"Starting new session {new_session}."
        )
        campaign["current_session"] = new_session
        save_campaign(campaign, campaign_json_path)
    else:
        print(f"Resuming session {current_session} (no turns recorded yet).")

    # Keep the current pointer up to date.
    set_current_campaign(campaign_json_path)

    # Render the template and write the hermes context file.
    rendered = render_template(campaign)
    HERMES_MD.write_text(rendered, encoding="utf-8")
    print(f"Campaign context written to: {HERMES_MD}")

    # Pass the campaign path through the environment so hermes tools can read it.
    env = os.environ.copy()
    env["LABYRINTH_CAMPAIGN"] = str(campaign_json_path)

    # Launch the hermes agent.
    hermes_cmd = [
        HERMES_BIN,
        "-t",
        "labyrinth,skills,memory",
        "-s",
        "language-labyrinth",
    ]
    print(f"Launching: {' '.join(hermes_cmd)}\n")
    try:
        result = subprocess.run(hermes_cmd, env=env)
        sys.exit(result.returncode)
    except FileNotFoundError:
        print(
            f"Error: hermes binary not found at {HERMES_BIN}.\n"
            "Ensure hermes-agent v0.12.0 is installed and the binary is at "
            "~/.local/bin/hermes.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: summary
# ---------------------------------------------------------------------------


def cmd_summary(args: argparse.Namespace) -> None:
    """Print a learning-progress summary for a campaign."""
    campaign_json_path = resolve_campaign_path(getattr(args, "campaign", None))
    campaign = load_campaign(campaign_json_path)

    turns: list[dict] = campaign.get("turns", [])
    vocabulary: list[dict] = campaign.get("vocabulary", [])

    # Sessions that have at least one turn are considered 'started'.
    sessions_with_turns: set[int] = {
        int(t["session"]) for t in turns if t.get("session") is not None
    }
    completed_sessions = len(sessions_with_turns)

    # Tally vocabulary entries by their acquisition reason.
    reason_counts: dict[str, int] = {}
    for entry in vocabulary:
        reason = entry.get("reason", "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    # Build a deduplicated word → translation mapping (first occurrence wins).
    unique_words: dict[str, str] = {}
    for entry in vocabulary:
        word = entry.get("word", "").strip()
        if word and word not in unique_words:
            unique_words[word] = entry.get("translation", "").strip()

    # --- Output ---
    print("=== Campaign Summary ===\n")
    print(f"  ID             : {campaign.get('campaign_id')}")
    print(
        f"  Player         : {campaign.get('player_name')} ({campaign.get('player_class')})"
    )
    print(
        f"  Language       : {campaign.get('target_language')} ({campaign.get('language_level')})"
    )
    print(
        f"  Progress       : session {campaign.get('current_session')} / {campaign.get('total_sessions')}"
    )
    print(f"  Sessions started: {completed_sessions}")
    print(f"  Total turns    : {len(turns)}")

    print(f"\n--- Vocabulary: {len(unique_words)} unique word(s) ---")
    if reason_counts:
        for reason, count in sorted(reason_counts.items()):
            print(f"  {reason}: {count}")
    else:
        print("  (no vocabulary recorded yet)")

    if unique_words:
        print()
        for word, translation in sorted(
            unique_words.items(), key=lambda kv: kv[0].lower()
        ):
            line = f"  {word}"
            if translation:
                line += f"  —  {translation}"
            print(line)

    print()


# ---------------------------------------------------------------------------
# Subcommand: use
# ---------------------------------------------------------------------------


def cmd_use(args: argparse.Namespace) -> None:
    """Activate a campaign by writing its path to the 'current' pointer file."""
    campaign_json_path = DATA_DIR / args.campaign_id / "campaign.json"
    if not campaign_json_path.exists():
        print(
            f"Error: No campaign found with id '{args.campaign_id}'.", file=sys.stderr
        )
        sys.exit(1)

    set_current_campaign(campaign_json_path)
    campaign = load_campaign(campaign_json_path)
    print(
        f"Active campaign set to: {args.campaign_id}\n"
        f"  Player  : {campaign.get('player_name')} ({campaign.get('player_class')})\n"
        f"  Language: {campaign.get('target_language')} ({campaign.get('language_level')})\n"
        f"  Session : {campaign.get('current_session')} / {campaign.get('total_sessions')}"
    )


# ---------------------------------------------------------------------------
# Argument parsing & dispatch
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Hermes Language Labyrinth — campaign launcher",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    sub.add_parser("create", help="Interactive wizard to create a new campaign")
    sub.add_parser("list", help="List all campaigns")

    play_p = sub.add_parser("play", help="Launch a hermes session for a campaign")
    play_p.add_argument(
        "--campaign",
        metavar="CAMPAIGN_ID",
        help="Campaign to play (defaults to the current active campaign)",
    )

    summary_p = sub.add_parser("summary", help="Show learning progress for a campaign")
    summary_p.add_argument(
        "--campaign",
        metavar="CAMPAIGN_ID",
        help="Campaign to summarise (defaults to the current active campaign)",
    )

    use_p = sub.add_parser("use", help="Set a campaign as the active campaign")
    use_p.add_argument(
        "campaign_id", metavar="CAMPAIGN_ID", help="Campaign ID to activate"
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "create": cmd_create,
        "list": cmd_list,
        "play": cmd_play,
        "summary": cmd_summary,
        "use": cmd_use,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
