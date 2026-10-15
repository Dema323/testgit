"""Run blocking calls (HTTP) off the UI thread and deliver results back on it."""
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .api import PlexError

_pending = set()  # keeps signal objects alive until their result is delivered


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn, signals):
        super().__init__()
        self.fn, self.signals = fn, signals

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001 - surfaced to the caller's on_error
            if not isinstance(e, PlexError):  # expected network errors aren't bugs
                traceback.print_exc()
            self.signals.failed.emit(e)
        else:
            self.signals.done.emit(result)


def _guard(callback, signals):
    def deliver(value):
        _pending.discard(signals)
        if callback is None:
            return
        try:
            callback(value)
        except RuntimeError as e:  # target widget was deleted while the call ran
            if "already deleted" not in str(e):
                raise
    return deliver


def run_async(fn, on_done=None, on_error=None):
    signals = _Signals()
    _pending.add(signals)
    signals.done.connect(_guard(on_done, signals))
    signals.failed.connect(_guard(on_error, signals))
    QThreadPool.globalInstance().start(_Task(fn, signals))
