"""
Hermes Language Labyrinth Plugin
=================================
Registers the three Language Labyrinth tools into hermes-agent's tool registry.

Loaded by hermes as module ``hermes_plugins.labyrinth``.
Tools file is symlinked/copied from the project repo's ``tools/labyrinth_tools.py``.
"""

from __future__ import annotations

import logging

from .tools import (
    GET_STORY_CONTEXT_SCHEMA,
    LOG_VOCABULARY_SCHEMA,
    SAVE_TURN_SCHEMA,
    handle_get_story_context,
    handle_log_vocabulary,
    handle_save_turn,
)

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Register all labyrinth tools. Called once by the plugin loader."""

    ctx.register_tool(
        name="log_vocabulary",
        toolset="labyrinth",
        schema=LOG_VOCABULARY_SCHEMA,
        handler=handle_log_vocabulary,
        description="Log a vocabulary item the DM used or the player misused.",
        emoji="📚",
    )
    ctx.register_tool(
        name="save_turn",
        toolset="labyrinth",
        schema=SAVE_TURN_SCHEMA,
        handler=handle_save_turn,
        description="Persist turn + vocab to disk. Call after every narration.",
        emoji="💾",
    )
    ctx.register_tool(
        name="get_story_context",
        toolset="labyrinth",
        schema=GET_STORY_CONTEXT_SCHEMA,
        handler=handle_get_story_context,
        description="Load campaign state at session start.",
        emoji="🗺️",
    )
    logger.info("Language Labyrinth plugin: 3 tools registered (labyrinth toolset)")
