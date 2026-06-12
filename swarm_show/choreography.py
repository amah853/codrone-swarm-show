from __future__ import annotations

from dataclasses import dataclass
import json
from math import cos, radians, sin, sqrt
from pathlib import Path
from typing import Any


DEFAULT_MAX_ORIGIN_RADIUS_FT = 10.0
REQUIRED_DRONE_COUNT = 6
MAX_HOVER_SECONDS = 0.6
CM_PER_FOOT = 30.48

ALLOWED_METHODS = {
    "hover",
    "move",
    "move_backward",
    "move_distance",
    "move_forward",
    "move_left",
    "move_right",
    "reset_move_values",
    "set_controller_LED",
    "set_controller_LED_mode",
    "set_drone_LED",
    "set_drone_LED_mode",
    "set_throttle",
    "turn_left",
    "turn_right",
}


@dataclass(frozen=True)
class Command:
    drone: int | str
    method: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] | None = None


@dataclass(frozen=True)
class Cue:
    name: str
    commands: tuple[Command, ...]
    mode: str = "parallel"
    post_delay: float = 0.0


@dataclass(frozen=True)
class Show:
    title: str
    expected_drones: int
    cues: tuple[Cue, ...]
    takeoff: bool = True
    land_on_finish: bool = True
    max_origin_radius_ft: float = DEFAULT_MAX_ORIGIN_RADIUS_FT
    vertical_axis_only: bool = False


class ChoreographyError(ValueError):
    """Raised when a show file is not safe to execute."""


def load_show(path: str | Path) -> Show:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_show(data)


def parse_show(data: dict[str, Any]) -> Show:
    expected_drones = _positive_int(data.get("expected_drones"), "expected_drones")
    if expected_drones != REQUIRED_DRONE_COUNT:
        raise ChoreographyError(f"show must use exactly {REQUIRED_DRONE_COUNT} drones")

    cues_data = data.get("cues")
    if not isinstance(cues_data, list) or not cues_data:
        raise ChoreographyError("show must include a non-empty cues list")

    cues = tuple(_parse_cue(cue_data, expected_drones, index) for index, cue_data in enumerate(cues_data))
    show = Show(
        title=_string(data.get("title", "Untitled show"), "title"),
        expected_drones=expected_drones,
        cues=cues,
        takeoff=bool(data.get("takeoff", True)),
        land_on_finish=bool(data.get("land_on_finish", True)),
        max_origin_radius_ft=_positive_number(
            data.get("max_origin_radius_ft", DEFAULT_MAX_ORIGIN_RADIUS_FT),
            "max_origin_radius_ft",
        ),
        vertical_axis_only=bool(data.get("vertical_axis_only", False)),
    )
    validate_axis_policy(show)
    validate_stability_policy(show)
    validate_projected_flight_box(show)
    return show


def build_sync(cue: Cue, expected_drones: int, swarm_module: Any) -> Any:
    sequences_by_index: dict[int, Any] = {}

    for command in cue.commands:
        drone_indices = range(expected_drones) if command.drone == "all" else [int(command.drone)]
        for drone_index in drone_indices:
            sequence = sequences_by_index.setdefault(drone_index, swarm_module.Sequence(drone_index))
            sequence.add(command.method, *command.args, **(command.kwargs or {}))

    if not sequences_by_index:
        raise ChoreographyError(f"cue '{cue.name}' has no executable commands")

    return swarm_module.Sync(*(sequences_by_index[index] for index in sorted(sequences_by_index)))


def describe_show(show: Show) -> str:
    lines = [
        f"Show: {show.title}",
        f"Expected drones: {show.expected_drones}",
        f"Max origin radius: {show.max_origin_radius_ft:g} ft",
        f"Vertical axis only: {show.vertical_axis_only}",
        f"Takeoff: {show.takeoff}",
        f"Land on finish: {show.land_on_finish}",
        "",
        "Cues:",
    ]
    for index, cue in enumerate(show.cues, start=1):
        lines.append(f"  {index}. {cue.name} ({cue.mode}, {len(cue.commands)} commands)")
        for command in cue.commands:
            target = "all" if command.drone == "all" else str(command.drone)
            args = ", ".join(repr(arg) for arg in command.args)
            kwargs = ", ".join(f"{key}={value!r}" for key, value in (command.kwargs or {}).items())
            call_parts = ", ".join(part for part in [args, kwargs] if part)
            lines.append(f"     drone {target}: {command.method}({call_parts})")
    return "\n".join(lines)


def _parse_cue(data: dict[str, Any], expected_drones: int, index: int) -> Cue:
    if not isinstance(data, dict):
        raise ChoreographyError(f"cue {index + 1} must be an object")

    commands_data = data.get("commands")
    if not isinstance(commands_data, list) or not commands_data:
        raise ChoreographyError(f"cue {index + 1} must include a non-empty commands list")

    mode = data.get("mode", "parallel")
    if mode != "parallel":
        raise ChoreographyError("only parallel cue execution is supported for emergency-stop responsiveness")

    return Cue(
        name=_string(data.get("name", f"Cue {index + 1}"), f"cue {index + 1} name"),
        commands=tuple(_parse_command(command, expected_drones, index) for command in commands_data),
        mode=mode,
        post_delay=_non_negative_number(data.get("post_delay", 0.0), f"cue {index + 1} post_delay"),
    )


def _parse_command(data: dict[str, Any], expected_drones: int, cue_index: int) -> Command:
    if not isinstance(data, dict):
        raise ChoreographyError(f"cue {cue_index + 1} command must be an object")

    drone = data.get("drone")
    if drone != "all":
        drone = _non_negative_int(drone, "drone")
        if drone >= expected_drones:
            raise ChoreographyError(f"drone index {drone} is outside expected range 0-{expected_drones - 1}")

    method = _string(data.get("method"), "method")
    if method not in ALLOWED_METHODS:
        allowed = ", ".join(sorted(ALLOWED_METHODS))
        raise ChoreographyError(f"method '{method}' is not allowed. Allowed methods: {allowed}")

    args = data.get("args", [])
    if not isinstance(args, list):
        raise ChoreographyError("args must be a list")
    kwargs = data.get("kwargs", {})
    if not isinstance(kwargs, dict):
        raise ChoreographyError("kwargs must be an object")

    _assert_json_scalar_tree(args, "args")
    _assert_json_scalar_tree(kwargs, "kwargs")

    return Command(drone=drone, method=method, args=tuple(args), kwargs=kwargs)


def validate_projected_flight_box(show: Show) -> None:
    max_radius_cm = show.max_origin_radius_ft * CM_PER_FOOT
    positions = {index: [0.0, 0.0, 0.0] for index in range(show.expected_drones)}
    headings = {index: 0.0 for index in range(show.expected_drones)}

    for cue in show.cues:
        for command in cue.commands:
            indices = range(show.expected_drones) if command.drone == "all" else [int(command.drone)]
            for drone_index in indices:
                _project_command(command, positions[drone_index], headings, drone_index)
                horizontal_radius = sqrt(positions[drone_index][0] ** 2 + positions[drone_index][1] ** 2)
                if horizontal_radius > max_radius_cm:
                    raise ChoreographyError(
                        f"cue '{cue.name}' projects drone {drone_index} {horizontal_radius / CM_PER_FOOT:.1f} ft "
                        f"from origin, beyond max_origin_radius_ft={show.max_origin_radius_ft:g}"
                    )


def validate_axis_policy(show: Show) -> None:
    if not show.vertical_axis_only:
        return

    for cue in show.cues:
        for command in cue.commands:
            _validate_vertical_axis_command(cue.name, command)


def validate_stability_policy(show: Show) -> None:
    for cue in show.cues:
        for command in cue.commands:
            if command.method == "hover":
                duration = _number_arg(command, 0, 0.0)
                if duration > MAX_HOVER_SECONDS:
                    raise ChoreographyError(
                        f"cue '{cue.name}' uses hover duration {duration:g}, "
                        f"but CoDrone EDU swarm cues limit hover to {MAX_HOVER_SECONDS:g}s"
                    )


def _validate_vertical_axis_command(cue_name: str, command: Command) -> None:
    if command.method in {"move_forward", "move_backward", "move_left", "move_right", "turn_left", "turn_right"}:
        raise ChoreographyError(
            f"cue '{cue_name}' uses {command.method}, but vertical_axis_only forbids horizontal/yaw movement"
        )
    if command.method == "move_distance":
        if len(command.args) < 3:
            raise ChoreographyError("move_distance requires x, y, z, velocity args")
        if float(command.args[0]) != 0 or float(command.args[1]) != 0:
            raise ChoreographyError(
                f"cue '{cue_name}' uses horizontal move_distance, but vertical_axis_only allows only z movement"
            )
    if command.method == "set_throttle":
        value = _number_arg(command, 0, None)
        if value < -45 or value > 45:
            raise ChoreographyError(
                f"cue '{cue_name}' uses throttle {value:g}, but vertical_axis_only limits throttle pulses to -45..45"
            )
    if command.method == "move":
        duration = _number_arg(command, 0, 0.0)
        if duration > 0.6:
            raise ChoreographyError(
                f"cue '{cue_name}' uses move duration {duration:g}, but vertical_axis_only limits pulses to 0.6s"
            )


def _project_command(
    command: Command,
    position_cm: list[float],
    headings: dict[int, float],
    drone_index: int,
) -> None:
    method = command.method
    if method == "turn_left":
        headings[drone_index] = (headings[drone_index] + _number_arg(command, 0, 90.0)) % 360
        return
    if method == "turn_right":
        headings[drone_index] = (headings[drone_index] - _number_arg(command, 0, 90.0)) % 360
        return
    if method == "move_distance":
        if len(command.args) < 3:
            raise ChoreographyError("move_distance requires x, y, z, velocity args")
        position_cm[0] += float(command.args[0]) * 100
        position_cm[1] += float(command.args[1]) * 100
        position_cm[2] += float(command.args[2]) * 100
        return
    distance = _movement_distance_cm(command)
    if distance is None:
        return

    local_heading = headings[drone_index]
    if method == "move_backward":
        local_heading += 180
    elif method == "move_left":
        local_heading += 90
    elif method == "move_right":
        local_heading -= 90

    angle = radians(local_heading)
    position_cm[0] += distance * cos(angle)
    position_cm[1] += distance * sin(angle)


def _movement_distance_cm(command: Command) -> float | None:
    if command.method not in {"move_forward", "move_backward", "move_left", "move_right"}:
        return None
    distance = _number_arg(command, 0, None)
    units = command.args[1] if len(command.args) > 1 else command.kwargs.get("units", "cm") if command.kwargs else "cm"
    if units == "cm":
        return distance
    if units == "ft":
        return distance * CM_PER_FOOT
    if units == "in":
        return distance * 2.54
    if units == "m":
        return distance * 100
    raise ChoreographyError(f"unsupported movement unit {units!r}")


def _number_arg(command: Command, index: int, default: float | None) -> float:
    if len(command.args) <= index:
        if default is None:
            raise ChoreographyError(f"{command.method} requires numeric arg {index}")
        return default
    value = command.args[index]
    if not isinstance(value, (int, float)):
        raise ChoreographyError(f"{command.method} arg {index} must be numeric")
    return float(value)


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChoreographyError(f"{field} must be a non-empty string")
    return value


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ChoreographyError(f"{field} must be a positive integer")
    return value


def _positive_number(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or value <= 0:
        raise ChoreographyError(f"{field} must be a positive number")
    return float(value)


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ChoreographyError(f"{field} must be a non-negative integer or 'all'")
    return value


def _non_negative_number(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or value < 0:
        raise ChoreographyError(f"{field} must be a non-negative number")
    return float(value)


def _assert_json_scalar_tree(value: Any, field: str) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_scalar_tree(item, f"{field}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ChoreographyError(f"{field} keys must be strings")
            _assert_json_scalar_tree(item, f"{field}.{key}")
        return
    raise ChoreographyError(f"{field} contains unsupported value {value!r}")
