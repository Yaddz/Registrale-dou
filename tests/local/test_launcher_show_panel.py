"""Segunda abertura do app: sinaliza a primeira instância (evento nomeado) em vez da caixa de mensagem.

Tudo com ``_kernel32`` falso: roda sem Windows real e sem criar objetos do sistema.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = ROOT / "windows" / "launcher.pyw"


@pytest.fixture
def launcher(monkeypatch):
    loader = importlib.machinery.SourceFileLoader("launcher_show_panel", str(LAUNCHER_PATH))
    spec = importlib.util.spec_from_loader("launcher_show_panel", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["launcher_show_panel"] = mod
    loader.exec_module(mod)
    monkeypatch.setattr(mod, "_is_windows", lambda: True)
    yield mod
    sys.modules.pop("launcher_show_panel", None)


class FakeKernel32:
    def __init__(self, open_handle=77, set_ok=True, waits=()):
        self.open_handle = open_handle
        self.set_ok = set_ok
        self.waits = list(waits)
        self.calls = []

    def CreateEventW(self, attrs, manual_reset, initial, name):
        self.calls.append(("CreateEventW", manual_reset, initial, name))
        return 55

    def OpenEventW(self, access, inherit, name):
        self.calls.append(("OpenEventW", access, name))
        return self.open_handle

    def SetEvent(self, handle):
        self.calls.append(("SetEvent", handle))
        return 1 if self.set_ok else 0

    def CloseHandle(self, handle):
        self.calls.append(("CloseHandle", handle))
        return 1

    def WaitForSingleObject(self, handle, timeout_ms):
        self.calls.append(("Wait", handle, timeout_ms))
        return self.waits.pop(0) if self.waits else 0x102


def test_create_show_panel_event_auto_reset_named_event(launcher, monkeypatch):
    k32 = FakeKernel32()
    monkeypatch.setattr(launcher, "_kernel32", lambda: k32)
    assert launcher.create_show_panel_event() == 55
    assert k32.calls == [("CreateEventW", False, False, "Local\\RegistraleDOU_ShowPanel")]


def test_signal_running_instance_opens_sets_and_closes_event(launcher, monkeypatch):
    k32 = FakeKernel32()
    monkeypatch.setattr(launcher, "_kernel32", lambda: k32)
    assert launcher.signal_running_instance() is True
    assert k32.calls == [
        ("OpenEventW", 0x0002, "Local\\RegistraleDOU_ShowPanel"),
        ("SetEvent", 77),
        ("CloseHandle", 77),
    ]


def test_signal_running_instance_old_instance_without_event_returns_false(launcher, monkeypatch):
    k32 = FakeKernel32(open_handle=None)
    monkeypatch.setattr(launcher, "_kernel32", lambda: k32)
    assert launcher.signal_running_instance() is False


def test_signal_running_instance_outside_windows_returns_false(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "_is_windows", lambda: False)
    monkeypatch.setattr(launcher, "_kernel32", lambda: pytest.fail("fora do Windows não usa kernel32"))
    assert launcher.signal_running_instance() is False
    assert launcher.create_show_panel_event() is None


def _main_second_instance(launcher, monkeypatch, signal_ok):
    boxes = []
    monkeypatch.setattr(launcher, "_configure_launcher_logging", lambda: None)
    monkeypatch.setattr(launcher, "acquire_launcher_mutex", lambda: (False, None))
    monkeypatch.setattr(launcher, "_show_message_box", lambda title, text: boxes.append(text))
    monkeypatch.setattr(launcher, "RegistraleTrayController", lambda **k: pytest.fail("segunda instância não sobe"))
    k32 = FakeKernel32(set_ok=signal_ok)
    monkeypatch.setattr(launcher, "_kernel32", lambda: k32)
    assert launcher.main([]) == 0
    return boxes


def test_main_second_instance_signals_first_without_message_box(launcher, monkeypatch):
    assert _main_second_instance(launcher, monkeypatch, signal_ok=True) == []


def test_main_second_instance_signal_failure_shows_message_box(launcher, monkeypatch):
    boxes = _main_second_instance(launcher, monkeypatch, signal_ok=False)
    assert len(boxes) == 1 and "já está aberto" in boxes[0]


def test_wait_show_panel_requests_calls_open_panel_on_signal_and_stops(launcher, monkeypatch):
    k32 = FakeKernel32(waits=[0x102, 0, 0x102, 0])
    monkeypatch.setattr(launcher, "_kernel32", lambda: k32)
    opened = []
    state = {"stop": False}

    def on_signal():
        opened.append(1)
        if len(opened) == 2:
            state["stop"] = True

    launcher.wait_show_panel_requests(55, on_signal, lambda: state["stop"], timeout_ms=1000)
    assert opened == [1, 1]
    assert all(c[2] == 1000 for c in k32.calls if c[0] == "Wait")


def test_wait_show_panel_requests_survives_open_panel_error_and_exits_on_wait_failure(launcher, monkeypatch):
    k32 = FakeKernel32(waits=[0, 0xFFFFFFFF])
    monkeypatch.setattr(launcher, "_kernel32", lambda: k32)

    def boom():
        raise RuntimeError("janela destruída")

    launcher.wait_show_panel_requests(55, boom, lambda: False)  # não levanta e sai no WAIT_FAILED
    assert [c[0] for c in k32.calls] == ["Wait", "Wait"]


def test_controller_listener_opens_panel_when_signaled(launcher, monkeypatch):
    k32 = FakeKernel32(waits=[0])
    monkeypatch.setattr(launcher, "_kernel32", lambda: k32)
    controller = launcher.RegistraleTrayController(open_browser_on_start=False)
    opened = []

    def fake_open_panel(*_a):
        opened.append(1)
        controller._stopping = True

    monkeypatch.setattr(controller, "open_panel", fake_open_panel)
    started = []
    monkeypatch.setattr(launcher.threading, "Thread", lambda target, args, **kw: started.append((target, args, kw))
                        or type("T", (), {"start": lambda self: target(*args)})())
    assert controller.start_show_panel_listener() is True
    assert started[0][2]["daemon"] is True
    assert opened == [1]
    assert controller._show_event == 55
