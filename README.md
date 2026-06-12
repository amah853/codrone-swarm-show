# CoDrone EDU Four-Drone Swarm Show

This is a local Python control station for a 4-drone CoDrone EDU show using Robolink's `codrone_edu.swarm` API.

It runs from the MacBook, connects to the USB-connected CoDrone EDU controllers, runs a cue-by-cue choreography, and keeps landing and emergency-stop controls active during flight.

## Setup

Use Python 3.11 or 3.12. Robolink's public docs require Python 3.8+ for swarm and `codrone-edu` 2.2 or newer; this project pins the current PyPI release, `codrone-edu==2.8`.

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Hardware Preflight

1. Charge all drone batteries.
2. Pair each drone with its own controller.
3. Connect the four controllers to the MacBook or a powered USB hub with data-capable USB cables.
4. Place the drones in a 2x2 coordinate launch box, 3-4 feet apart from each neighbor, all parallel and facing the same direction. After connection, the program sets both drone and controller LEDs to these setup colors:

```text
                 FRONT

          drone 0 RED       3-4 ft       drone 1 ORANGE


          drone 2 YELLOW    3-4 ft       drone 3 GREEN

                 PILOT / MACBOOK
```

5. Keep the flight area indoors, open, below 10 ft, and away from students, walls, liquids, and fragile objects. For classroom use, mark a no-student zone around the entire flight area.

## Dry Run

Dry-run mode validates and prints the show without connecting to drones:

```bash
python -m swarm_show --show choreographies/four_drone_show.json
```

## Fly

This command connects the swarm, requires exactly four detected controllers, colors the drones/controllers, prints the setup diagram, prompts you to type `DONE`, starts the keyboard safety controls, then runs the choreography.

```bash
python -m swarm_show --show choreographies/four_drone_show.json --arm
```

During flight:

- Press `L` in the terminal to land every drone normally.
- Press `E` in the terminal to emergency stop.
- Press `Enter` in the terminal to emergency stop.
- Type `STOP` and press `Enter` to emergency stop.
- Press `Ctrl-C` to emergency stop.

Emergency stop cuts the motors immediately. Prefer `L` for normal landing whenever the drones are still controllable.

The show starts from that launch box, performs a synchronized backflip, uses short vertical throttle pulses, runs a timed up/down wave, does one second synchronized backflip, beeps together, then lands. Animated LED modes are avoided in the default show because each drone can run those effects slightly out of sync. The CoDrone EDU library skips flips if a drone battery is under 50%, so charge all drones before running it.

## Safety Limits

The choreography includes `max_origin_radius_ft`, currently set to `10`. The loader rejects a show file if the projected relative path for any drone moves more than that far from its starting point.

The default routine intentionally uses much smaller moves than that limit. The 10 ft radius is a guardrail for future choreography edits, not a target.

The default choreography sets `vertical_axis_only: true`. With that enabled, the loader rejects horizontal movement commands, heading changes, yaw/turn commands, and overly long or strong throttle pulses. The show uses `set_throttle(...)`, `move(...)`, and `reset_move_values()` for short relative vertical pulses instead of coordinate positioning.

## Crash Detection

The public CoDrone EDU Python API does not provide one direct "crash callback." This controller uses the available signals:

- `get_accident_count()` before and during the show.
- `get_angle_x()`, `get_angle_y()`, and `get_bottom_range()` between cues.

If a drone's accident count increases, or if it appears severely tilted while very low to the ground after a cue, the controller sends `land()` to the full swarm. This is best-effort and cue-boundary based, so keep using the keyboard controls and visual supervision.

## Customize The Show

Edit `choreographies/four_drone_show.json`.

Each cue has a name and commands:

```json
{
  "name": "blue blink",
  "commands": [
    { "drone": "all", "method": "set_drone_LED_mode", "args": [0, 80, 255, "blink", 5] },
    { "drone": "all", "method": "hover", "args": [1.0] }
  ]
}
```

Supported methods are intentionally allow-listed in `swarm_show/choreography.py` so a show file cannot call arbitrary library methods. The current allow-list includes short vertical pulse controls, basic movement, turns, LEDs, hover, buzzer notes, and `flip`.

## References

- Robolink Swarm Function Documentation: `Swarm`, `connect`, `Sequence`, `Sync`, and `run`.
- Robolink Drone Function Documentation: `takeoff`, `land`, `hover`, movement commands, LEDs, `get_accident_count`, sensor functions, and `emergency_stop`.
- CoDrone EDU manual safety notes: indoor use, spacing, line-of-sight, normal landing as safest stop, emergency stop only when needed.
