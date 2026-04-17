"""System tray icon - run ActionShot minimized in the Windows tray."""

import os
import sys
import threading

try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

from .recorder import Recorder


def _create_icon_image(recording: bool = False) -> "Image.Image":
    """Create a simple tray icon image."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if recording:
        # Red circle when recording
        draw.ellipse([4, 4, size - 4, size - 4], fill="#e94560", outline="white", width=2)
        # Inner dot
        draw.ellipse([20, 20, size - 20, size - 20], fill="white")
    else:
        # Blue circle when idle
        draw.ellipse([4, 4, size - 4, size - 4], fill="#0f3460", outline="white", width=2)
        # Lightning bolt
        draw.polygon([(28, 12), (20, 32), (30, 32), (24, 52), (42, 26), (32, 26), (38, 12)], fill="#FFD600")

    return img


class TrayApp:
    """System tray application for ActionShot."""

    def __init__(self, output_dir: str = "recordings"):
        if not HAS_PYSTRAY:
            raise ImportError("pystray not installed. Run: pip install pystray")

        self.output_dir = output_dir
        self.recorder = None
        self.recording = False
        self.icon = None
        self._step_updater = None

    def run(self):
        self.icon = pystray.Icon(
            "ActionShot",
            _create_icon_image(False),
            "ActionShot - Ready",
            menu=pystray.Menu(
                Item("Start Recording", self._toggle_recording, default=True),
                Item("Open Recordings", self._open_recordings),
                Item("Launch GUI", self._launch_gui),
                pystray.Menu.SEPARATOR,
                Item("Quit", self._quit),
            ),
        )

        print("  ActionShot running in system tray.")
        print("  Right-click the tray icon for options.")
        self.icon.run()

    def _toggle_recording(self, icon=None, item=None):
        if not self.recording:
            self.recording = True
            self.recorder = Recorder(output_dir=self.output_dir)

            if self.icon:
                self.icon.icon = _create_icon_image(True)
                self.icon.title = "ActionShot - Recording..."

            def _record():
                self.recorder.start()
                self.recording = False
                if self._step_updater:
                    self._step_updater.cancel()
                    self._step_updater = None
                if self.icon:
                    self.icon.icon = _create_icon_image(False)
                    self.icon.title = "ActionShot - Ready"

            threading.Thread(target=_record, daemon=True).start()
            self._start_step_counter()
        else:
            if self.recorder:
                self.recorder.stop()
            self.recording = False
            if self.icon:
                self.icon.icon = _create_icon_image(False)
                self.icon.title = "ActionShot - Ready"

    def _open_recordings(self, icon=None, item=None):
        path = os.path.abspath(self.output_dir)
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

    def _launch_gui(self, icon=None, item=None):
        from .gui import ActionShotGUI
        threading.Thread(target=lambda: ActionShotGUI().run(), daemon=True).start()

    def _start_step_counter(self):
        """Periodically update tray tooltip with step count."""
        import threading

        def _update():
            if self.recording and self.recorder and self.recorder.session and self.icon:
                count = self.recorder.session.step_count
                self.icon.title = f"ActionShot - Recording ({count} steps)"
                self._step_updater = threading.Timer(1.0, _update)
                self._step_updater.daemon = True
                self._step_updater.start()

        _update()

    def _quit(self, icon=None, item=None):
        if self._step_updater:
            self._step_updater.cancel()
        if self.recording and self.recorder:
            self.recorder.stop()
        if self.icon:
            self.icon.stop()
