from __future__ import annotations

"""Adapter that bridges android_world AsyncEnv with the local Environment interface.

It leverages `android_world.env.env_launcher.load_and_setup_env` to connect to an
already-running emulator and exposes the same `create / step / save / load /
remove` API expected by `EnvironmentWorker`.
"""

import dataclasses
import time
import uuid
from typing import Any, Dict

from environment.base import Environment
from utils.logging import setup_logger

logger = setup_logger()

try:
    from android_world.env import env_launcher
    from android_world.env import json_action as aw_json
    from android_world.env import representation_utils as aw_repr
    from environment.action_utils import to_json_action
except Exception as import_err:  # pragma: no cover
    # Catch the error early, but don't break module import time.
    logger.warning(f"android_world dependencies not available: {import_err}")
    env_launcher = None  # type: ignore


class AndroidWorldAsyncEnvironment(Environment):
    """Wraps `android_world`'s `AsyncEnv` into the local `Environment` API."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        if env_launcher is None:
            raise RuntimeError(
                "android_world library not available – cannot initialise AndroidWorldAsyncEnvironment"
            )

        console_port = config.get("console_port", 5554)
        adb_path = config.get("adb_path", "~/Android/Sdk/platform-tools/adb")
        grpc_port = config.get("grpc_port", 8554)
        emulator_setup = config.get("emulator_setup", False)
        freeze_datetime = config.get("freeze_datetime", True)

        logger.info(
            "Loading AndroidWorld AsyncEnv (console_port=%s, grpc_port=%s)",
            console_port,
            grpc_port,
        )
        self._env = env_launcher.load_and_setup_env(
            console_port=console_port,
            emulator_setup=emulator_setup,
            freeze_datetime=freeze_datetime,
            adb_path=adb_path,
            grpc_port=grpc_port,
        )

        # Track active trajectories
        self._trajectories: Dict[str, float] = {}

    # ---------------------------------------------------------------------
    # Environment API implementation
    # ---------------------------------------------------------------------

    def create(self) -> Dict[str, Any]:
        """Starts a new logical trajectory (does not relaunch emulator)."""
        trajectory_id = str(uuid.uuid4())
        self._env.reset(go_home=True)
        self._trajectories[trajectory_id] = time.time()
        logger.info("Created new trajectory %s", trajectory_id)
        return {"success": True, "trajectory_id": trajectory_id}

    # For AndroidWorld env we don't rely on snapshotting; implement no-ops.
    def save(self, trajectory_id: str) -> Dict[str, Any]:
        if trajectory_id not in self._trajectories:
            return {"success": False, "error": "Unknown trajectory_id"}
        # No snapshotting yet – could integrate emulator snapshots later.
        return {"success": True, "message": "Save not implemented – noop"}

    def load(self, trajectory_id: str) -> Dict[str, Any]:
        if trajectory_id in self._trajectories:
            return {"success": True, "trajectory_id": trajectory_id}
        return {"success": False, "error": "Unknown trajectory_id"}

    def remove(self, trajectory_id: str) -> Dict[str, Any]:
        if trajectory_id in self._trajectories:
            del self._trajectories[trajectory_id]
            return {"success": True}
        return {"success": False, "error": "Unknown trajectory_id"}

    # ------------------------------------------------------------------
    # Step logic – supports both JSONAction & simple text commands.
    # ------------------------------------------------------------------

    def step(self, trajectory_id: str, action: Any) -> Dict[str, Any]:
        if trajectory_id not in self._trajectories:
            return {"success": False, "error": "Unknown trajectory_id"}

        try:
            json_action = to_json_action(action)
            self._env.execute_action(json_action)

            # Wait a bit to allow UI to settle.
            time.sleep(0.5)
            state = self._env.get_state(wait_to_stabilize=True)
            observation = {
                "pixels": state.pixels.tolist() if hasattr(state.pixels, "tolist") else state.pixels,
                "ui_elements": [dataclasses.asdict(el) for el in state.ui_elements],
                "current_activity": self._env.foreground_activity_name,
                "screen_size": self._env.device_screen_size,
                "orientation": self._env.orientation if hasattr(self._env, "orientation") else None,
            }
            self._trajectories[trajectory_id] = time.time()
            return {"success": True, "observation": observation}
        except Exception as exc:
            logger.error("Failed to execute action: %s", exc)
            return {"success": False, "error": str(exc)} 