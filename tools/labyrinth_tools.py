"""
Hermes Language Labyrinth — Tool Handlers

Three tools that back the Language Labyrinth DM skill:

  log_vocabulary      – buffer a vocab entry for the current turn
  save_turn           – persist turn + buffered vocab to campaign JSON
  get_story_context   – return current campaign state for session start

All handlers follow the hermes-agent convention:
  signature  : (args: dict, **kwargs) -> str
  return     : json.dumps(...)  — never a raw dict, never raise
  kwargs     : task_id (str) for per-session state isolation
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _data_dir() -> Path:
    """Return the labyrinth data directory, creating it if absent."""
    env = os.environ.get("LABYRINTH_DATA_DIR", "").strip()
    if env:
        path = Path(env).expanduser()
    else:
        try:
            from hermes_cli.config import cfg_get, load_config

            config = load_config()
            raw = cfg_get(
                config,
                "skills",
                "config",
                "labyrinth",
                "data_dir",
                default="~/.hermes/labyrinth",
            )
        except Exception:
            raw = "~/.hermes/labyrinth"
        path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _current_campaign_path() -> Path | None:
    """Return path to the active campaign JSON, or None if not set."""
    # 1. Explicit env var set by main.py launcher
    env = os.environ.get("LABYRINTH_CAMPAIGN", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p

    # 2. Pointer file written by main.py
    pointer = _data_dir() / "current"
    if pointer.exists():
        target = Path(pointer.read_text(encoding="utf-8").strip()).expanduser()
        if target.exists():
            return target

    return None


# ---------------------------------------------------------------------------
# In-memory vocab buffer  (keyed by task_id for per-session isolation)
# ---------------------------------------------------------------------------

_vocab_lock = threading.Lock()
_vocab_buffers: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# log_vocabulary
# ---------------------------------------------------------------------------

LOG_VOCABULARY_SCHEMA: dict = {
    "name": "log_vocabulary",
    "description": (
        "Log a vocabulary item encountered during narration. "
        "Call when: (1) you use a word the player is unlikely to know at their CEFR level, "
        "(2) you correct a misused word implicitly, "
        "(3) a low-frequency but story-relevant word appears."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "word": {
                "type": "string",
                "description": "The word or phrase in the target language.",
            },
            "translation": {
                "type": "string",
                "description": "Translation into the player's native language.",
            },
            "reason": {
                "type": "string",
                "enum": ["new_word", "misused_by_player", "low_frequency"],
                "description": (
                    "new_word: word introduced that player unlikely knows; "
                    "misused_by_player: player used it incorrectly (implicit correction); "
                    "low_frequency: rare word relevant to the story."
                ),
            },
            "example_sentence": {
                "type": "string",
                "description": "The sentence from narration where the word appeared.",
            },
        },
        "required": ["word", "translation", "reason", "example_sentence"],
    },
}


def handle_log_vocabulary(args: dict, **kwargs: Any) -> str:
    word = args.get("word", "").strip()
    translation = args.get("translation", "").strip()
    reason = args.get("reason", "new_word")
    example_sentence = args.get("example_sentence", "").strip()
    task_id = kwargs.get("task_id", "default")

    if not word:
        return json.dumps({"error": "word is required"})

    valid_reasons = {"new_word", "misused_by_player", "low_frequency"}
    if reason not in valid_reasons:
        return json.dumps({"error": f"reason must be one of {sorted(valid_reasons)}"})

    entry = {
        "word": word,
        "translation": translation,
        "reason": reason,
        "example_sentence": example_sentence,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    with _vocab_lock:
        _vocab_buffers.setdefault(task_id, []).append(entry)

    logger.debug("log_vocabulary: %s (%s) [task=%s]", word, reason, task_id)
    return json.dumps({"status": "logged", "word": word})


# ---------------------------------------------------------------------------
# save_turn
# ---------------------------------------------------------------------------

SAVE_TURN_SCHEMA: dict = {
    "name": "save_turn",
    "description": (
        "Persist the current turn (player input + DM narration) to disk. "
        "Must be called at the end of EVERY narration response, no exceptions. "
        "Bundles any vocabulary logged via log_vocabulary during this turn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "player_input": {
                "type": "string",
                "description": "The player's raw input text for this turn.",
            },
            "narration": {
                "type": "string",
                "description": "The DM's narration response for this turn.",
            },
        },
        "required": ["player_input", "narration"],
    },
}


def handle_save_turn(args: dict, **kwargs: Any) -> str:
    player_input = args.get("player_input", "").strip()
    narration = args.get("narration", "").strip()
    task_id = kwargs.get("task_id", "default")

    if not narration:
        return json.dumps({"error": "narration is required"})

    # Drain vocab buffer for this task
    with _vocab_lock:
        vocab_this_turn = _vocab_buffers.pop(task_id, [])

    campaign_path = _current_campaign_path()
    if campaign_path is None:
        return json.dumps(
            {"error": "No active campaign. Start a session via main.py play."}
        )

    try:
        data: dict = json.loads(campaign_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return json.dumps({"error": f"Could not read campaign file: {exc}"})

    current_session: int = data.get("current_session", 1)
    turns: list = data.setdefault("turns", [])
    all_vocab: list = data.setdefault("vocabulary", [])

    turn_number = len([t for t in turns if t.get("session") == current_session]) + 1
    turn_record = {
        "session": current_session,
        "turn": turn_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "player_input": player_input,
        "narration": narration,
        "vocabulary": vocab_this_turn,
    }
    turns.append(turn_record)
    all_vocab.extend(vocab_this_turn)

    # Update story summary to the last narration (lightweight rolling summary)
    data["last_narration"] = narration[:400]

    try:
        campaign_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        return json.dumps({"error": f"Could not write campaign file: {exc}"})

    logger.info(
        "save_turn: session=%d turn=%d vocab=%d [task=%s]",
        current_session,
        turn_number,
        len(vocab_this_turn),
        task_id,
    )
    return json.dumps(
        {
            "status": "saved",
            "turn": turn_number,
            "session": current_session,
            "vocab_logged": len(vocab_this_turn),
        }
    )


# ---------------------------------------------------------------------------
# get_story_context
# ---------------------------------------------------------------------------

GET_STORY_CONTEXT_SCHEMA: dict = {
    "name": "get_story_context",
    "description": (
        "Load current campaign state at the start of a session. "
        "Returns act name, session number, story summary, and session target. "
        "Call once at the very start of each session before writing any narration."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def handle_get_story_context(args: dict, **kwargs: Any) -> str:  # noqa: ARG001
    campaign_path = _current_campaign_path()
    if campaign_path is None:
        return json.dumps(
            {
                "error": (
                    "No active campaign. Ask the player to start a session via: "
                    "python main.py play"
                )
            }
        )

    try:
        data: dict = json.loads(campaign_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return json.dumps({"error": f"Could not read campaign file: {exc}"})

    current_session = data.get("current_session", 1)
    act_name = data.get("act_name", "")

    # Resolve act goals and beats from acts list if present
    acts: list = data.get("acts", [])
    act_goals: list[str] = []
    act_beats: list[str] = []
    for act in acts:
        if act.get("name") == act_name:
            act_goals = act.get("narrative_goals", [])
            act_beats = act.get("suggested_beats", [])
            break

    story_summary = data.get("story_summary", "")
    if not story_summary:
        story_summary = data.get("last_narration", "No story yet — this is session 1.")

    return json.dumps(
        {
            "current_session": current_session,
            "total_sessions": data.get("total_sessions", 10),
            "act_name": act_name,
            "story_summary": story_summary,
            "session_target_minutes": data.get("session_target_minutes", 30.0),
            "player_name": data.get("player_name", ""),
            "player_class": data.get("player_class", ""),
            "target_language": data.get("target_language", ""),
            "language_level": data.get("language_level", ""),
            "native_language": data.get("native_language", "English"),
            "act_narrative_goals": act_goals,
            "act_suggested_beats": act_beats,
            "turns_this_session": len(
                [
                    t
                    for t in data.get("turns", [])
                    if t.get("session") == current_session
                ]
            ),
        },
        ensure_ascii=False,
    )
