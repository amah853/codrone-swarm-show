import pytest

from swarm_show.choreography import ChoreographyError, build_sync, parse_show


class FakeSequence:
    def __init__(self, index):
        self.index = index
        self.commands = []

    def add(self, method, *args, **kwargs):
        self.commands.append((method, args, kwargs))


class FakeSync:
    def __init__(self, *sequences):
        self.sequences = sequences


class FakeSwarmModule:
    Sequence = FakeSequence
    Sync = FakeSync


def test_parse_valid_show_and_expand_all_command():
    show = parse_show(
        {
            "title": "Test",
            "expected_drones": 6,
            "cues": [
                {
                    "name": "blink",
                    "commands": [
                        {"drone": "all", "method": "hover", "args": [0.5]},
                        {"drone": 2, "method": "turn_left", "args": [90]},
                    ],
                }
            ],
        }
    )

    sync = build_sync(show.cues[0], show.expected_drones, FakeSwarmModule)

    assert [sequence.index for sequence in sync.sequences] == [0, 1, 2, 3, 4, 5]
    assert sync.sequences[0].commands == [("hover", (0.5,), {})]
    assert sync.sequences[2].commands == [("hover", (0.5,), {}), ("turn_left", (90,), {})]


def test_rejects_arbitrary_method():
    with pytest.raises(ChoreographyError, match="not allowed"):
        parse_show(
            {
                "title": "Bad",
                "expected_drones": 6,
                "cues": [
                    {
                        "name": "bad",
                        "commands": [{"drone": "all", "method": "__getattribute__", "args": []}],
                    }
                ],
            }
        )


def test_rejects_out_of_range_drone_index():
    with pytest.raises(ChoreographyError, match="outside expected range"):
        parse_show(
            {
                "title": "Bad",
                "expected_drones": 6,
                "cues": [
                    {
                        "name": "bad",
                        "commands": [{"drone": 6, "method": "hover", "args": [1]}],
                    }
                ],
            }
        )


def test_rejects_non_six_drone_show():
    with pytest.raises(ChoreographyError, match="exactly 6 drones"):
        parse_show(
            {
                "title": "Bad count",
                "expected_drones": 5,
                "cues": [
                    {
                        "name": "hover",
                        "commands": [{"drone": "all", "method": "hover", "args": [1]}],
                    }
                ],
            }
        )


def test_rejects_projected_path_outside_flight_box():
    with pytest.raises(ChoreographyError, match="beyond max_origin_radius_ft"):
        parse_show(
            {
                "title": "Too wide",
                "expected_drones": 6,
                "max_origin_radius_ft": 1,
                "cues": [
                    {
                        "name": "too far",
                        "commands": [{"drone": 0, "method": "move_forward", "args": [2, "ft"]}],
                    }
                ],
            }
        )


def test_rejects_long_hover_commands():
    with pytest.raises(ChoreographyError, match="limit hover"):
        parse_show(
            {
                "title": "Too much drift",
                "expected_drones": 6,
                "cues": [
                    {
                        "name": "long hover",
                        "commands": [{"drone": "all", "method": "hover", "args": [1.0]}],
                    }
                ],
            }
        )


def test_rejects_old_flip_demo_commands():
    with pytest.raises(ChoreographyError, match="not allowed"):
        parse_show(
            {
                "title": "Flip",
                "expected_drones": 6,
                "cues": [
                    {
                        "name": "flip",
                        "commands": [{"drone": "all", "method": "flip", "args": ["back"]}],
                    }
                ],
            }
        )


def test_allows_vertical_pulse_commands():
    show = parse_show(
        {
            "title": "Vertical pulse",
            "expected_drones": 6,
            "vertical_axis_only": True,
            "cues": [
                {
                    "name": "pulse",
                    "commands": [
                        {"drone": "all", "method": "set_throttle", "args": [30]},
                        {"drone": "all", "method": "move", "args": [0.25]},
                        {"drone": "all", "method": "reset_move_values", "args": []},
                    ],
                }
            ],
        }
    )

    sync = build_sync(show.cues[0], show.expected_drones, FakeSwarmModule)

    assert sync.sequences[0].commands == [
        ("set_throttle", (30,), {}),
        ("move", (0.25,), {}),
        ("reset_move_values", (), {}),
    ]


def test_rejects_buzzer_commands():
    with pytest.raises(ChoreographyError, match="not allowed"):
        parse_show(
            {
                "title": "No audio",
                "expected_drones": 6,
                "cues": [
                    {
                        "name": "buzzer",
                        "commands": [{"drone": "all", "method": "controller_buzzer", "args": [784, 120]}],
                    }
                ],
            }
        )


def test_rejects_coordinate_commands():
    with pytest.raises(ChoreographyError, match="not allowed"):
        parse_show(
            {
                "title": "Coordinates",
                "expected_drones": 6,
                "cues": [
                    {
                        "name": "coords",
                        "commands": [
                            {
                                "drone": "all",
                                "method": "send_absolute_position",
                                "args": [0.0, 0.0, 1.0, 0.5, 0, 0],
                            }
                        ],
                    }
                ],
            }
        )


def test_vertical_axis_only_allows_throttle_pulses():
    show = parse_show(
        {
            "title": "Vertical",
            "expected_drones": 6,
            "vertical_axis_only": True,
            "cues": [
                {
                    "name": "z",
                    "commands": [
                        {"drone": "all", "method": "set_throttle", "args": [-25]},
                        {"drone": "all", "method": "move", "args": [0.2]},
                        {"drone": "all", "method": "reset_move_values", "args": []},
                    ],
                }
            ],
        }
    )

    sync = build_sync(show.cues[0], show.expected_drones, FakeSwarmModule)

    assert sync.sequences[0].commands == [
        ("set_throttle", (-25,), {}),
        ("move", (0.2,), {}),
        ("reset_move_values", (), {}),
    ]


def test_vertical_axis_only_rejects_large_throttle_pulse():
    with pytest.raises(ChoreographyError, match="limits throttle pulses"):
        parse_show(
            {
                "title": "Bad vertical",
                "expected_drones": 6,
                "vertical_axis_only": True,
                "cues": [
                    {
                        "name": "bad",
                        "commands": [{"drone": "all", "method": "set_throttle", "args": [70]}],
                    }
                ],
            }
        )


def test_vertical_axis_only_rejects_long_move_pulse():
    with pytest.raises(ChoreographyError, match="limits pulses"):
        parse_show(
            {
                "title": "Bad vertical",
                "expected_drones": 6,
                "vertical_axis_only": True,
                "cues": [
                    {
                        "name": "bad",
                        "commands": [{"drone": "all", "method": "move", "args": [1.2]}],
                    }
                ],
            }
        )


def test_vertical_axis_only_rejects_horizontal_movement_commands():
    with pytest.raises(ChoreographyError, match="vertical_axis_only forbids"):
        parse_show(
            {
                "title": "Bad vertical",
                "expected_drones": 6,
                "vertical_axis_only": True,
                "cues": [
                    {
                        "name": "bad",
                        "commands": [{"drone": "all", "method": "move_right", "args": [10, "cm", 0.5]}],
                    }
                ],
            }
        )
