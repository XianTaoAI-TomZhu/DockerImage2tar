import sys
import time
from typing import Optional


class ProgressBar:
    def __init__(self, total: int = 100, desc: str = "Downloading", unit: str = "B", quiet: bool = False):
        self.total = total
        self.desc = desc
        self.unit = unit
        self.quiet = quiet
        self.current = 0
        self.start_time = time.time()
        self._last_update = 0

    def update(self, n: int = 1):
        self.current += n
        if self.quiet:
            return
        current_time = time.time()
        if current_time - self._last_update < 0.1 and self.current < self.total:
            return
        self._last_update = current_time
        self._display()

    def set_description(self, desc: str):
        self.desc = desc

    def _display(self):
        elapsed = time.time() - self.start_time
        percent = (self.current / self.total * 100) if self.total > 0 else 0

        bar_length = 30
        filled = int(bar_length * self.current / self.total) if self.total > 0 else 0
        bar = "=" * filled + "-" * (bar_length - filled)

        speed = self.current / elapsed if elapsed > 0 else 0
        speed_str = self._format_size(speed) + "/s"

        sys.stdout.write(f"\r{self.desc}: [{bar}] {percent:.1f}% {self._format_size(self.current)}/{self._format_size(self.total)} {speed_str}")
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def close(self):
        if not self.quiet and self.current < self.total:
            self._display()


class DownloadProgressTracker:
    def __init__(self, total_size: int, quiet: bool = False):
        self.total_size = total_size
        self.downloaded_size = 0
        self.start_time = time.time()
        self.quiet = quiet

    def update(self, size: int):
        self.downloaded_size += size

    def get_stats(self) -> dict:
        elapsed = time.time() - self.start_time
        speed = self.downloaded_size / elapsed if elapsed > 0 else 0
        percent = (self.downloaded_size / self.total_size * 100) if self.total_size > 0 else 0

        return {
            "downloaded": self.downloaded_size,
            "total": self.total_size,
            "percent": percent,
            "speed": speed,
            "elapsed": elapsed
        }

    def print_summary(self):
        stats = self.get_stats()
        print(f"\n📊 下载统计:")
        print(f"   总大小: {self._format_size(stats['downloaded'])}")
        print(f"   平均速度: {self._format_size(stats['speed'])}/s")
        print(f"   总耗时: {stats['elapsed']:.1f}秒")

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
