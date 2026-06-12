# CoDrone EDU Six-Drone Swarm Show

This is a local Python control station for a 6-drone CoDrone EDU show using Robolink's `codrone_edu.swarm` API.

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
3. Connect the six controllers to the MacBook or a powered USB hub with data-capable USB cables.
4. Place the drones in the marked six-drone launch layout, 3-4 feet apart from each neighbor, all parallel and facing the same direction. After connection, the program sets both drone and controller LEDs to these setup colors:

```text
                 FRONT

                    drone 0 RED

          drone 1 ORANGE             drone 2 YELLOW


          drone 3 GREEN              drone 4 BLUE

                  drone 5 PURPLE

                 PILOT / MACBOOK
```

5. Keep the flight area indoors, open, below 10 ft, and away from students, walls, liquids, and fragile objects. For classroom use, mark a no-student zone around the entire flight area.

## Dry Run

Dry-run mode validates and prints the show without connecting to drones:

```bash
python -m swarm_show --show choreographies/six_drone_show.json
```

## Fly

This command connects the swarm, requires exactly six detected controllers, colors the drones/controllers, prints the setup diagram, prompts you to type `DONE`, starts the keyboard safety controls, then runs the choreography.

```bash
python -m swarm_show --show choreographies/six_drone_show.json --arm
```

During flight:

- Press `L` in the terminal to land every drone normally.
- Press `E` in the terminal to emergency stop.
- Press `Enter` in the terminal to emergency stop.
- Type `STOP` and press `Enter` to emergency stop.
- Press `Ctrl-C` to emergency stop.

Emergency stop cuts the motors immediately. Prefer `L` for normal landing whenever the drones are still controllable.

The show takes off together, runs a startup altitude check, moves through a loose hexagon, clears center, runs a V pass-through, a synchronized wave, an LED chase, one DNA-style twist, then finishes with a lane-lift firework return and lands together. The terminal prints an act banner as each act starts. The choreography is staged as short pass-through motion instead of held geometric shapes because CoDrone EDU drones do not have formation lock. Audio, buzzer, countdown, orchestra, pixel-art holds, and flip-demo commands are not part of the supported choreography surface.

## Safety Limits

The choreography includes `max_origin_radius_ft`, currently set to `5`. The loader rejects a show file if the projected relative path for any drone moves more than that far from its starting point.

The default routine intentionally uses much smaller moves than that limit. The radius is a guardrail for future choreography edits, not a target.

The default choreography uses simple relative `move_distance(...)` commands, low velocities, two-radius staging, short hover commands, and only startup plus mid-show altitude checks for camp-safe pass-through movement. The loader rejects hover commands longer than 0.6 seconds and still validates the projected flight box before a show can run.

## Crash Detection

The public CoDrone EDU Python API does not provide one direct "crash callback." This controller uses the available signals:

- `get_accident_count()` before and during the show.
- `get_angle_x()`, `get_angle_y()`, and `get_bottom_range()` between cues.

If a drone's accident count increases, or if it appears severely tilted while very low to the ground after a cue, the controller sends `land()` to the full swarm. This is best-effort and cue-boundary based, so keep using the keyboard controls and visual supervision.

## Customize The Show

Edit `choreographies/six_drone_show.json`.

Each cue has a name and commands:

```json
{
  "name": "blue blink",
  "commands": [
    { "drone": "all", "method": "set_drone_LED_mode", "args": [0, 80, 255, "blink", 5] },
    { "drone": "all", "method": "hover", "args": [0.5] }
  ]
}
```

Supported methods are intentionally allow-listed in `swarm_show/choreography.py` so a show file cannot call arbitrary library methods. The current allow-list includes short vertical pulse controls, basic movement, turns, LEDs, and hover. Buzzer/audio and flip commands are intentionally rejected.

## References

- Robolink Swarm Function Documentation: `Swarm`, `connect`, `Sequence`, `Sync`, and `run`.
- Robolink Drone Function Documentation: `takeoff`, `land`, `hover`, movement commands, LEDs, `get_accident_count`, sensor functions, and `emergency_stop`.
- CoDrone EDU manual safety notes: indoor use, spacing, line-of-sight, normal landing as safest stop, emergency stop only when needed.
