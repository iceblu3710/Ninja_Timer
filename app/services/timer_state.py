"""Pure timer state transition logic."""
from enum import StrEnum


class TimerState(StrEnum):
    IDLE = "IDLE"
    READY = "READY"
    COUNTDOWN = "COUNTDOWN"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    SAVED = "SAVED"
    FALSE_START = "FALSE_START"
    SENSOR_FAULT = "SENSOR_FAULT"
    MANUAL_STOPPED = "MANUAL_STOPPED"
    DNF = "DNF"
    ERROR = "ERROR"


class InvalidTimerTransition(ValueError):
    """Raised when a timer event is not valid for the current state."""


class TimerStateMachine:
    """Small, dependency-free state machine for timer commands."""

    _TRANSITIONS: dict[TimerState, dict[str, TimerState]] = {
        TimerState.IDLE: {
            "arm": TimerState.READY,
            "manual_start": TimerState.RUNNING,
            "hardware_fault": TimerState.SENSOR_FAULT,
        },
        TimerState.READY: {
            "start_command": TimerState.RUNNING,
            "countdown_start": TimerState.COUNTDOWN,
            "start_sensor_triggered": TimerState.RUNNING,
            "reset": TimerState.IDLE,
            "hardware_fault": TimerState.SENSOR_FAULT,
        },
        TimerState.COUNTDOWN: {
            "countdown_complete": TimerState.RUNNING,
            "start_sensor_triggered_before_go": TimerState.FALSE_START,
            "reset": TimerState.IDLE,
        },
        TimerState.RUNNING: {
            "finish_sensor_triggered": TimerState.FINISHED,
            "manual_stop": TimerState.MANUAL_STOPPED,
            "dnf": TimerState.DNF,
            "reset": TimerState.IDLE,
            "hardware_fault": TimerState.SENSOR_FAULT,
        },
        TimerState.FINISHED: {
            "save_run": TimerState.SAVED,
            "delete_run": TimerState.IDLE,
            "reset": TimerState.IDLE,
        },
        TimerState.SAVED: {
            "next_runner": TimerState.READY,
            "reset": TimerState.IDLE,
        },
        TimerState.FALSE_START: {
            "reset": TimerState.IDLE,
            "rearm": TimerState.READY,
        },
        TimerState.SENSOR_FAULT: {
            "clear_fault": TimerState.IDLE,
            "manual_mode": TimerState.IDLE,
        },
        TimerState.MANUAL_STOPPED: {
            "reset": TimerState.IDLE,
        },
        TimerState.DNF: {
            "reset": TimerState.IDLE,
        },
        TimerState.ERROR: {
            "reset": TimerState.IDLE,
        },
    }

    def __init__(self, initial_state: TimerState = TimerState.IDLE):
        self.state = initial_state

    def can(self, event: str) -> bool:
        return event in self._TRANSITIONS.get(self.state, {})

    def transition(self, event: str) -> TimerState:
        next_state = self._TRANSITIONS.get(self.state, {}).get(event)
        if next_state is None:
            raise InvalidTimerTransition(
                f"Cannot apply event {event!r} while timer is {self.state.value}."
            )
        self.state = next_state
        return self.state

    def reset(self) -> TimerState:
        if self.state == TimerState.IDLE:
            return self.state
        return self.transition("reset")
