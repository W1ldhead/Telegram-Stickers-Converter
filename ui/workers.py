"""Фоновая работа: анализ добавленных файлов и очередь конвертации."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from core.convert import ConvertError, convert_file
from core.encode import CancelToken, Cancelled, Plan
from core.probe import ProbeError, VideoInfo, probe


class Prober(QObject):
    """ffprobe в пуле потоков, результат — сигналом в окно."""
    probed = Signal(object, object)    # ключ, VideoInfo
    failed = Signal(object, str)       # ключ, текст

    def __init__(self) -> None:
        super().__init__()
        self._pool = ThreadPoolExecutor(max_workers=2)

    def submit(self, key: object, path: Path) -> None:
        self._pool.submit(self._run, key, path)

    def _run(self, key: object, path: Path) -> None:
        try:
            info = probe(path)
        except ProbeError as e:
            self.failed.emit(key, str(e))
        except Exception as e:  # noqa: BLE001 — любая неожиданность = файл не прочитан
            self.failed.emit(key, f"Не удалось прочитать файл: {e}")
        else:
            self.probed.emit(key, info)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


@dataclass
class Job:
    key: object
    src: Path
    out_dir: Path
    plan: Plan
    info: VideoInfo


class ConvertThread(QThread):
    """Файлы по очереди; ошибка одного не останавливает остальные."""
    file_started = Signal(object)
    file_progress = Signal(object, float)
    file_done = Signal(object, object)          # ключ, convert.Result
    file_failed = Signal(object, str, str)      # ключ, текст, хвост журнала ffmpeg
    file_cancelled = Signal(object)

    def __init__(self, jobs: list[Job]) -> None:
        super().__init__()
        self.jobs = jobs
        self.token = CancelToken()

    def cancel(self) -> None:
        self.token.cancel()

    def run(self) -> None:
        for job in self.jobs:
            if self.token.cancelled:
                break
            self.file_started.emit(job.key)
            try:
                result = convert_file(
                    job.src, job.out_dir, job.plan, self.token,
                    progress=lambda f, k=job.key: self.file_progress.emit(k, f),
                    info=job.info,
                )
            except Cancelled:
                self.file_cancelled.emit(job.key)
                break
            except ConvertError as e:
                self.file_failed.emit(job.key, str(e), e.log_tail)
            except Exception as e:  # noqa: BLE001 — не роняем очередь из-за одного файла
                self.file_failed.emit(job.key, f"Ошибка: {e}", "")
            else:
                self.file_done.emit(job.key, result)
