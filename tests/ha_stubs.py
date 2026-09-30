"""Schlanke Home-Assistant-Stubs für Controller-Tests ohne installiertes HA.

Nur so viel API, wie der Controller (custom_components/pv_management_fix/
__init__.py) tatsächlich benutzt. Ist das echte homeassistant-Paket
installiert, werden die Stubs NICHT verwendet.
"""
from __future__ import annotations

import enum
import sys
import types
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=2))


class Clock:
    """Steuerbare Uhr für dt_util.now()/utcnow()."""

    now = datetime(2026, 9, 30, 12, 0, tzinfo=TZ)


def install() -> bool:
    """Registriert die Stubs in sys.modules. False, wenn echtes HA vorhanden."""
    try:
        import homeassistant  # noqa: F401
        if not getattr(homeassistant, "__pv_stub__", False):
            return False
    except ImportError:
        pass
    if "homeassistant" in sys.modules:
        return True

    ha = types.ModuleType("homeassistant")
    ha.__pv_stub__ = True
    ha.__path__ = []

    const = types.ModuleType("homeassistant.const")
    const.STATE_UNAVAILABLE = "unavailable"
    const.STATE_UNKNOWN = "unknown"

    class Platform(str, enum.Enum):
        SENSOR = "sensor"
        BUTTON = "button"
        BINARY_SENSOR = "binary_sensor"

    const.Platform = Platform

    core = types.ModuleType("homeassistant.core")

    def callback(func):
        return func

    core.callback = callback
    core.HomeAssistant = object
    core.Event = object

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object

    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    dt = types.ModuleType("homeassistant.util.dt")
    dt.now = lambda: Clock.now
    dt.utcnow = lambda: Clock.now.astimezone(timezone.utc)
    dt.parse_datetime = lambda s: datetime.fromisoformat(s)
    util.dt = dt

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    event = types.ModuleType("homeassistant.helpers.event")

    def _unsub():
        return lambda: None

    event.async_call_later = lambda hass, delay, action: _unsub()
    event.async_track_state_change_event = lambda hass, ids, action: _unsub()
    event.async_track_time_change = lambda hass, action, **kw: _unsub()
    event.async_track_time_interval = lambda hass, action, interval: _unsub()
    helpers.event = event

    for name, mod in {
        "homeassistant": ha,
        "homeassistant.const": const,
        "homeassistant.core": core,
        "homeassistant.config_entries": config_entries,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": event,
    }.items():
        sys.modules[name] = mod
    return True


class FakeState:
    def __init__(self, state, attributes=None):
        self.state = str(state)
        self.attributes = attributes or {}


class FakeStates:
    def __init__(self):
        self._states = {}

    def set(self, entity_id, state, attributes=None):
        self._states[entity_id] = FakeState(state, attributes)

    def get(self, entity_id):
        return self._states.get(entity_id)


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, data=None):
        self.events.append((event_type, data))


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data):
        self.calls.append((domain, service, data))


class FakeConfigEntries:
    def async_update_entry(self, entry, options=None):
        if options is not None:
            entry.options = dict(options)


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.bus = FakeBus()
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries()
        self.data = {}

    def async_create_task(self, coro):
        # Service-Aufrufe sofort ausführen (synchron, ohne Event-Loop)
        try:
            coro.send(None)
        except StopIteration:
            pass


class FakeEntry:
    def __init__(self, data=None, options=None):
        self.entry_id = "test_entry"
        self.data = dict(data or {})
        self.options = dict(options or {})
