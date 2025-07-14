from __future__ import annotations

"""Shared utilities for converting user action representations to `android_world.env.json_action.JSONAction`.

This centralises DSL→JSONAction parsing so that both `AndroidEnvironment` (legacy)
 and `AndroidWorldAsyncEnvironment` use exactly the same rules.
"""

from typing import Any
import json

from android_world.env import json_action as aw_json

__all__ = ["to_json_action", "dsl_to_json_action"]


def to_json_action(action: Any) -> aw_json.JSONAction:  # type: ignore
    """Converts *action* (dict / JSON string / DSL string / JSONAction) into JSONAction."""
    if isinstance(action, aw_json.JSONAction):
        return action
    if isinstance(action, dict):
        return aw_json.JSONAction(**action)
    if isinstance(action, str):
        stripped = action.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return aw_json.JSONAction(**json.loads(stripped))
        return dsl_to_json_action(stripped)
    raise ValueError(f"Unsupported action type: {type(action)}")


def dsl_to_json_action(cmd: str) -> aw_json.JSONAction:  # type: ignore
    """Very small DSL -> JSONAction mapping compatible with legacy commands.

    Examples:
        click 100 200
        swipe 100 200 300 400
        text "Hello World"
        key back / key home / key enter
    """
    parts = cmd.split()
    if not parts:
        raise ValueError("Empty action command")
    t = parts[0].lower()
    if t == "click" and len(parts) >= 3:
        return aw_json.JSONAction(action_type=aw_json.CLICK, x=int(parts[1]), y=int(parts[2]))

    if t == "text":
        text = " ".join(parts[1:])
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return aw_json.JSONAction(action_type=aw_json.INPUT_TEXT, text=text)

    if t == "swipe" and len(parts) >= 5:
        # Heuristic: derive direction from coordinates
        x1, y1, x2, y2 = map(int, parts[1:5])
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) > abs(dy):
            direction = "right" if dx > 0 else "left"
        else:
            direction = "down" if dy > 0 else "up"
        return aw_json.JSONAction(action_type=aw_json.SWIPE, direction=direction)

    if t == "key" and len(parts) >= 2:
        key = parts[1].lower()
        if key == "back":
            return aw_json.JSONAction(action_type=aw_json.NAVIGATE_BACK)
        if key == "home":
            return aw_json.JSONAction(action_type=aw_json.NAVIGATE_HOME)
        if key == "enter":
            return aw_json.JSONAction(action_type=aw_json.KEYBOARD_ENTER)

    raise ValueError(f"Cannot parse action DSL: {cmd}") 