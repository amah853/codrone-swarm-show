from swarm_show.control import FlightAbortController, _apply_setup_colors


class FakeSwarm:
    def __init__(self):
        self.calls = []

    def land(self):
        self.calls.append(("land",))

    def emergency_stop(self):
        self.calls.append(("emergency_stop",))

    def run_drone(self, index, method, *args):
        self.calls.append(("run_drone", index, method, args))


def test_landing_request_uses_land_not_emergency_stop():
    swarm = FakeSwarm()
    controller = FlightAbortController(swarm, expected_drones=4)

    controller.request_landing("test")

    assert controller.landing_requested
    assert not controller.emergency_stop_triggered
    assert swarm.calls == [("land",)]


def test_emergency_request_uses_emergency_stop():
    swarm = FakeSwarm()
    controller = FlightAbortController(swarm, expected_drones=4)

    controller.trigger_emergency_stop("test")

    assert controller.emergency_stop_triggered
    assert swarm.calls == [("emergency_stop",)]


def test_setup_colors_match_physical_layout():
    swarm = FakeSwarm()

    _apply_setup_colors(swarm, expected_drones=4)

    assert swarm.calls == [
        ("run_drone", 0, "set_drone_LED", (255, 0, 0, 255)),
        ("run_drone", 0, "set_controller_LED", (255, 0, 0, 255)),
        ("run_drone", 1, "set_drone_LED", (255, 120, 0, 255)),
        ("run_drone", 1, "set_controller_LED", (255, 120, 0, 255)),
        ("run_drone", 2, "set_drone_LED", (255, 230, 0, 255)),
        ("run_drone", 2, "set_controller_LED", (255, 230, 0, 255)),
        ("run_drone", 3, "set_drone_LED", (0, 255, 80, 255)),
        ("run_drone", 3, "set_controller_LED", (0, 255, 80, 255)),
    ]
