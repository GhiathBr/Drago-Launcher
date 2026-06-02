import threading
import time
import requests


class NetworkMonitor:
    def __init__(self, check_url="https://launchercontent.mojang.com/news.json", interval=15):
        self.check_url = check_url
        self.interval = interval
        self._online = False
        self._prev_online = False
        self._running = False
        self._thread = None
        self._listeners = []

    def start(self):
        if self._running:
            return
        self._running = True
        self._online = self._check()
        self._prev_online = self._online
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def is_online(self) -> bool:
        return self._online

    def was_offline(self) -> bool:
        return not self._prev_online and self._online

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _check(self) -> bool:
        try:
            resp = requests.get(self.check_url, timeout=3)
            return resp.status_code < 500
        except Exception:
            return False

    def _poll(self):
        while self._running:
            self._online = self._check()
            if self._online and not self._prev_online:
                for cb in self._listeners:
                    try:
                        cb()
                    except Exception:
                        pass
            self._prev_online = self._online
            time.sleep(self.interval)
