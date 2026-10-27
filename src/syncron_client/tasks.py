"""Exécution des appels réseau hors du thread de l'interface.

`TaskRunner.run(fn, on_done, on_error)` exécute `fn` dans le pool de threads de
Qt puis rappelle `on_done(résultat)` ou `on_error(exception)` dans le thread
de l'interface. `ImmediateRunner` exécute tout de suite (tests).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

Done = Callable[[Any], None]
Failed = Callable[[Exception], None]


class _Relay(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any], relay: _Relay) -> None:
        super().__init__()
        self._fn = fn
        self._relay = relay

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:
            self._relay.failed.emit(exc)
        else:
            self._relay.done.emit(result)


class TaskRunner:
    def __init__(self, pool: QThreadPool | None = None) -> None:
        self._pool = pool or QThreadPool.globalInstance()
        self._alive: set[_Relay] = set()

    def run(self, fn: Callable[[], Any], on_done: Done | None = None, on_error: Failed | None = None) -> None:
        relay = _Relay()
        self._alive.add(relay)

        def finish(handler, value) -> None:
            self._alive.discard(relay)
            relay.deleteLater()
            if handler is not None:
                handler(value)

        relay.done.connect(lambda value: finish(on_done, value))
        relay.failed.connect(lambda exc: finish(on_error, exc))
        self._pool.start(_Job(fn, relay))

    def wait(self, timeout_ms: int = 30_000) -> bool:
        return self._pool.waitForDone(timeout_ms)


class ImmediateRunner(TaskRunner):
    def __init__(self) -> None:
        super().__init__()

    def run(self, fn: Callable[[], Any], on_done: Done | None = None, on_error: Failed | None = None) -> None:
        try:
            result = fn()
        except Exception as exc:
            if on_error is not None:
                on_error(exc)
            return
        if on_done is not None:
            on_done(result)

    def wait(self, timeout_ms: int = 30_000) -> bool:
        return True
