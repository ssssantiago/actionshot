"""Video recording - captures screen as MP4 alongside screenshots."""

import os
import time
import threading

import cv2
import numpy as np
import pyautogui


class VideoRecorder:
    """Records the screen to an MP4 file in a background thread."""

    def __init__(self, output_path: str, fps: int = 10, monitor: int = 0):
        self.output_path = output_path
        self.fps = fps
        self.monitor = monitor
        self._running = False
        self._paused = False
        self._thread = None
        self._writer = None

    def start(self):
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._writer:
            self._writer.release()
            self._writer = None

    def _record_loop(self):
        screen_size = pyautogui.size()
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(
            self.output_path, fourcc, self.fps,
            (screen_size.width, screen_size.height),
        )

        interval = 1.0 / self.fps

        while self._running:
            if self._paused:
                time.sleep(0.1)
                continue

            start_t = time.perf_counter()

            try:
                screenshot = pyautogui.screenshot()
                frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                self._writer.write(frame)
            except Exception:
                pass

            elapsed = time.perf_counter() - start_t
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        if self._writer:
            self._writer.release()
            self._writer = None
