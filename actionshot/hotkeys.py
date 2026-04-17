"""Global hotkeys for controlling ActionShot without focus."""

import threading
from pynput import keyboard


class HotkeyManager:
    """Manages global hotkeys for record start/stop/pause."""

    DEFAULT_HOTKEYS = {
        "toggle_record": {keyboard.Key.shift, keyboard.Key.cmd, keyboard.KeyCode.from_char("r")},
        "pause_record": {keyboard.Key.shift, keyboard.Key.cmd, keyboard.KeyCode.from_char("p")},
        "stop_record": {keyboard.Key.shift, keyboard.Key.cmd, keyboard.KeyCode.from_char("s")},
    }

    def __init__(self, callbacks: dict = None):
        """
        callbacks: dict mapping action name to callable, e.g.:
            {"toggle_record": my_toggle_fn, "pause_record": my_pause_fn}
        """
        self.callbacks = callbacks or {}
        self.hotkeys = dict(self.DEFAULT_HOTKEYS)
        self._pressed = set()
        self._listener = None
        self._running = False

    def start(self):
        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        self._running = False
        if self._listener:
            self._listener.stop()

    def _on_press(self, key):
        if not self._running:
            return
        self._pressed.add(key)
        self._check_hotkeys()

    def _on_release(self, key):
        self._pressed.discard(key)

    def _check_hotkeys(self):
        for action, combo in self.hotkeys.items():
            if combo.issubset(self._pressed):
                cb = self.callbacks.get(action)
                if cb:
                    threading.Thread(target=cb, daemon=True).start()
                    self._pressed.clear()
                    break

    def set_hotkey(self, action: str, keys: set):
        self.hotkeys[action] = keys
