from __future__ import annotations

from dataclasses import dataclass
import signal
import select
import sys
import termios
import threading
import time
import tty
from types import FrameType
from typing import Any

from .choreography import Show, build_sync


SETUP_COLORS = (
    (0, "red", (255, 0, 0, 255)),
    (1, "orange", (255, 120, 0, 255)),
    (2, "yellow", (255, 230, 0, 255)),
    (3, "green", (0, 255, 80, 255)),
    (4, "blue", (0, 120, 255, 255)),
    (5, "purple", (170, 70, 255, 255)),
)

SETUP_DIAGRAM = """\
Setup layout, coordinate launch box, all drones facing forward:

                 FRONT

                    drone 0 RED

          drone 1 ORANGE             drone 2 YELLOW


          drone 3 GREEN              drone 4 BLUE

                  drone 5 PURPLE

                 PILOT / MACBOOK
"""


@dataclass
class RunOptions:
    require_confirmation: bool = True
    connect_pause: bool = False


class GracefulLandingRequested(RuntimeError):
    """Raised when the operator or crash monitor has already requested landing."""


class FlightAbortController:
    def __init__(self, swarm: Any, expected_drones: int) -> None:
        self._swarm = swarm
        self._expected_drones = expected_drones
        self._emergency_stop_triggered = threading.Event()
        self._landing_requested = threading.Event()
        self._stop_listener = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def emergency_stop_triggered(self) -> bool:
        return self._emergency_stop_triggered.is_set()

    @property
    def landing_requested(self) -> bool:
        return self._landing_requested.is_set()

    def start_keyboard_listener(self) -> None:
        self._thread = threading.Thread(target=self._watch_keyboard, name="flight-abort-listener", daemon=True)
        self._thread.start()

    def stop_keyboard_listener(self) -> None:
        self._stop_listener.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)

    def request_landing(self, reason: str) -> None:
        with self._lock:
            if self._landing_requested.is_set() or self._emergency_stop_triggered.is_set():
                return
            self._landing_requested.set()
            print(f"\nLANDING REQUESTED: {reason}")
            try:
                self._swarm.land()
                return
            except Exception as exc:
                print(f"Bulk land failed: {exc!r}; trying each drone individually.")

            for index in range(self._expected_drones):
                try:
                    self._swarm.run_drone(index, "land")
                except Exception as exc:
                    print(f"Drone {index} land failed: {exc!r}")

    def trigger_emergency_stop(self, reason: str) -> None:
        with self._lock:
            if self._emergency_stop_triggered.is_set():
                return
            self._emergency_stop_triggered.set()
            print(f"\nEMERGENCY STOP: {reason}")
            try:
                self._swarm.emergency_stop()
                return
            except Exception as exc:
                print(f"Bulk emergency_stop failed: {exc!r}; trying each drone individually.")

            for index in range(self._expected_drones):
                try:
                    self._swarm.run_drone(index, "emergency_stop")
                except Exception as exc:
                    print(f"Drone {index} emergency_stop failed: {exc!r}")

    def _watch_keyboard(self) -> None:
        print("Flight controls armed: press L to land, E/Enter to emergency stop, or Ctrl-C.")
        if sys.stdin.isatty():
            self._watch_raw_keyboard()
        else:
            self._watch_line_keyboard()

    def _watch_raw_keyboard(self) -> None:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while (
                not self._stop_listener.is_set()
                and not self._landing_requested.is_set()
                and not self._emergency_stop_triggered.is_set()
            ):
                readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not readable:
                    continue
                char = sys.stdin.read(1)
                if char.lower() == "l":
                    self.request_landing("operator pressed L")
                    return
                if char.lower() == "e" or char in {"\n", "\r"}:
                    self.trigger_emergency_stop("operator requested emergency stop")
                    return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _watch_line_keyboard(self) -> None:
        while (
            not self._stop_listener.is_set()
            and not self._landing_requested.is_set()
            and not self._emergency_stop_triggered.is_set()
        ):
            line = sys.stdin.readline()
            if line == "":
                return
            command = line.strip().upper()
            if command == "L":
                self.request_landing("operator typed L")
                return
            if command in {"", "E", "STOP"}:
                self.trigger_emergency_stop("operator requested emergency stop")
                return


def run_show(show: Show, swarm_module: Any, options: RunOptions | None = None) -> None:
    options = options or RunOptions()
    swarm = swarm_module.Swarm(enable_color=True, enable_print=True, enable_pause=options.connect_pause)
    abort_controller: FlightAbortController | None = None
    airborne = False
    previous_sigint_handler = signal.getsignal(signal.SIGINT)
    crash_baseline: list[int | None] = []

    try:
        print("Connecting to CoDrone EDU controllers...")
        swarm.connect()
        connected = _connected_drone_count(swarm)
        if connected != show.expected_drones:
            raise RuntimeError(f"Expected {show.expected_drones} drones, but Swarm connected {connected}.")

        print(f"Connected {connected} drones.")
        _apply_setup_colors(swarm, show.expected_drones)
        if options.require_confirmation:
            _confirm_setup(show)

        crash_baseline = _read_accident_counts(swarm, show.expected_drones)
        abort_controller = FlightAbortController(swarm, show.expected_drones)

        def handle_sigint(signum: int, frame: FrameType | None) -> None:
            abort_controller.trigger_emergency_stop("Ctrl-C")
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, handle_sigint)
        abort_controller.start_keyboard_listener()

        if show.takeoff:
            _raise_if_aborted(abort_controller)
            print("Taking off...")
            swarm.takeoff()
            airborne = True

        current_act: str | None = None
        for cue_number, cue in enumerate(show.cues, start=1):
            _raise_if_aborted(abort_controller)
            act = _cue_act_label(cue.name)
            if act is not None and act != current_act:
                current_act = act
                print()
                print(f"=== {act.upper()} ===")
            print(f"Running cue {cue_number}/{len(show.cues)}: {cue.name}")
            sync = build_sync(cue, show.expected_drones, swarm_module)
            swarm.run(sync, type=cue.mode)
            _check_for_crash_signal(swarm, show.expected_drones, crash_baseline, abort_controller)
            _sleep_interruptibly(cue.post_delay, abort_controller)

        if airborne and show.land_on_finish and not abort_controller.emergency_stop_triggered:
            print("Landing...")
            swarm.land()
            airborne = False

    except GracefulLandingRequested:
        airborne = False
        print("Show stopped after landing request.")
    except KeyboardInterrupt:
        if abort_controller is not None:
            abort_controller.trigger_emergency_stop("KeyboardInterrupt")
        raise SystemExit(130)
    except Exception:
        if airborne and abort_controller is not None and not abort_controller.emergency_stop_triggered:
            abort_controller.trigger_emergency_stop("unexpected show error")
        raise
    finally:
        signal.signal(signal.SIGINT, previous_sigint_handler)
        if abort_controller is not None:
            abort_controller.stop_keyboard_listener()
        try:
            print("Disconnecting swarm...")
            swarm.disconnect()
        except Exception as exc:
            print(f"Disconnect failed: {exc!r}")


def _apply_setup_colors(swarm: Any, expected_drones: int) -> None:
    if expected_drones != len(SETUP_COLORS):
        raise RuntimeError(f"Setup supports exactly {len(SETUP_COLORS)} drones.")

    print()
    print("Assigning setup colors...")
    for index, color_name, rgba in SETUP_COLORS[:expected_drones]:
        r, g, b, brightness = rgba
        print(f"- drone {index}: {color_name}")
        swarm.run_drone(index, "set_drone_LED", r, g, b, brightness)
        swarm.run_drone(index, "set_controller_LED", r, g, b, brightness)
    print()


def _confirm_setup(show: Show) -> None:
    print()
    print(SETUP_DIAGRAM)
    print("Confirm the physical setup:")
    print("- Drones are indoors, below 10 ft, and at least 3-4 feet apart.")
    print("- Students are outside the marked flight zone; no people, walls, liquids, or fragile objects are nearby.")
    print("- Drone/controller colors match the coordinate launch box diagram exactly.")
    print("- All drones are parallel and face forward in the same direction.")
    print("- Terminal focus stays here so L can land and E, Enter, or Ctrl-C can emergency stop.")
    print()
    answer = input(f"Type DONE once the setup is correct to arm '{show.title}': ")
    if answer.strip().upper() != "DONE":
        raise RuntimeError("Flight was not armed.")


def _connected_drone_count(swarm: Any) -> int:
    if hasattr(swarm, "_num_drones"):
        return int(swarm._num_drones)
    if hasattr(swarm, "get_drones"):
        return len(swarm.get_drones())
    raise RuntimeError("Unable to determine connected drone count from Swarm object.")


def _cue_act_label(cue_name: str) -> str | None:
    prefix, separator, _ = cue_name.partition(" - ")
    if separator and prefix.lower().startswith("act "):
        return prefix
    return None


def _raise_if_aborted(abort_controller: FlightAbortController) -> None:
    if abort_controller.emergency_stop_triggered:
        raise KeyboardInterrupt
    if abort_controller.landing_requested:
        raise GracefulLandingRequested


def _sleep_interruptibly(seconds: float, abort_controller: FlightAbortController) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _raise_if_aborted(abort_controller)
        time.sleep(min(0.1, deadline - time.monotonic()))


def _read_accident_counts(swarm: Any, expected_drones: int) -> list[int | None]:
    counts: list[int | None] = []
    for index in range(expected_drones):
        try:
            counts.append(int(swarm.run_drone(index, "get_accident_count")))
        except Exception as exc:
            print(f"Crash monitor: could not read drone {index} accident count: {exc!r}")
            counts.append(None)
    return counts


def _check_for_crash_signal(
    swarm: Any,
    expected_drones: int,
    accident_baseline: list[int | None],
    abort_controller: FlightAbortController,
) -> None:
    if abort_controller.landing_requested or abort_controller.emergency_stop_triggered:
        _raise_if_aborted(abort_controller)

    for index in range(expected_drones):
        try:
            accident_count = int(swarm.run_drone(index, "get_accident_count"))
            if accident_baseline[index] is not None and accident_count > accident_baseline[index]:
                abort_controller.request_landing(f"drone {index} accident count increased")
                raise GracefulLandingRequested
            accident_baseline[index] = accident_count
        except GracefulLandingRequested:
            raise
        except Exception as exc:
            print(f"Crash monitor: could not read drone {index} accident count: {exc!r}")

        if _looks_crashed_or_tipped(swarm, index):
            abort_controller.request_landing(f"drone {index} appears tipped or down")
            raise GracefulLandingRequested


def _looks_crashed_or_tipped(swarm: Any, index: int) -> bool:
    try:
        angle_x = float(swarm.run_drone(index, "get_angle_x"))
        angle_y = float(swarm.run_drone(index, "get_angle_y"))
        height_cm = float(swarm.run_drone(index, "get_bottom_range", "cm"))
    except Exception as exc:
        print(f"Crash monitor: could not read drone {index} tilt/height: {exc!r}")
        return False

    severely_tilted = abs(angle_x) >= 65 or abs(angle_y) >= 65
    very_low = 0 < height_cm <= 8
    return severely_tilted and very_low
