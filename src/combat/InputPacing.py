from contextlib import contextmanager
from contextvars import ContextVar
from random import uniform
from time import monotonic


SAME_CONTROL_INTERVAL_RANGE = (0.150, 0.170)
ACTION_INTERVAL_RANGE = (0.080, 0.090)
TAP_DURATION_RANGE = (0.035, 0.045)
SWITCH_RETRY_INTERVAL_RANGE = (0.420, 0.480)
_active = ContextVar('combat_input_pacing', default=None)


class CombatInputPacing:
    def __init__(self, sleep, clock=monotonic):
        self.sleep = sleep
        self.clock = clock
        self.last_action = float('-inf')
        self.last_by_control = {}

    def before_press(self, kind, control):
        control = (kind, str(control).casefold())
        action_interval = uniform(*ACTION_INTERVAL_RANGE)
        same_control_interval = uniform(*SAME_CONTROL_INTERVAL_RANGE)
        while True:
            earliest_press = max(self.last_action + action_interval,
                                 self.last_by_control.get(control, float('-inf')) + same_control_interval)
            now = self.clock()
            remaining = earliest_press - now
            if remaining <= 0.000001:
                break
            self.sleep(remaining)
        self.last_action = now
        self.last_by_control[control] = now

    @contextmanager
    def active(self):
        token = _active.set(self)
        try:
            yield
        finally:
            _active.reset(token)


def before_press(kind, control):
    if (pacing := _active.get()) is not None:
        pacing.before_press(kind, control)


def tap_duration(duration):
    if _active.get() is None or duration >= TAP_DURATION_RANGE[1]:
        return duration
    return max(duration, uniform(*TAP_DURATION_RANGE))


def switch_retry_interval():
    return uniform(*SWITCH_RETRY_INTERVAL_RANGE)
