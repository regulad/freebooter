"""
    freebooter downloads photos & videos from the internet and uploads it onto your social media accounts.
    Copyright (C) 2023 Parker Wahle

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
from __future__ import annotations

from logging import getLogger, Logger
from threading import Lock, Thread, Event

from ..file_management import ScratchFile, FileManager
from ..metadata import MediaMetadata
from ..middlewares import Middleware


class Uploader(Thread):
    """
    Base class for all uploaders. Uploaders are responsible for uploading media to social media platforms.
    They are a thread to allow the execution of background tasks.
    """

    BACKGROUND_TASK_INTERVAL_SECONDS: float = 1.0

    def __init__(self, name: str, preprocessors: list[Middleware], **config) -> None:
        super().__init__(
            name=f"{self.__class__.__name__}-{name.title().replace(' ', '-')}"
        )

        self._upload_lock = Lock()
        self._shutdown_event: Event | None = None
        self._file_manager: FileManager | None = None
        self.preprocessors = preprocessors

    def start(self) -> None:
        for middleware in self.preprocessors:
            middleware.start()
        super().start()

    def background_task(self) -> None:
        """
        Override this method to implement a background task.
        """
        pass

    def run(self) -> None:
        assert self.ready, "Uploader is not ready!"
        assert self._shutdown_event is not None, "Uploader is not ready!"

        while not self._shutdown_event.is_set():
            self.background_task()
            self._shutdown_event.wait(self.BACKGROUND_TASK_INTERVAL_SECONDS)

    @property
    def logger(self) -> Logger:
        return getLogger(self.name)

    @property
    def ready(self) -> bool:
        return (
            self._shutdown_event is not None
            and self._file_manager is not None
            and all(middleware.ready for middleware in self.preprocessors)
        )

    def prepare(self, shutdown_event: Event, file_manager: FileManager) -> None:
        assert not self.ready, "Uploader is already ready!"

        self._shutdown_event = shutdown_event
        self._file_manager = file_manager

        for middleware in self.preprocessors:
            middleware.prepare(shutdown_event, file_manager)

        assert self.ready, "Uploader failed to prepare."

    def upload(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        raise NotImplementedError

    def upload_and_preprocess(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        for middleware in self.preprocessors:
            medias = middleware.process_many(medias)
        with self._upload_lock:
            try:
                return self.upload(medias)
            except Exception as e:
                self.logger.exception(e)
                return []

    def close(self) -> None:
        for middleware in self.preprocessors:
            middleware.close()

    def join(self, timeout: float | None = None) -> None:
        for middleware in self.preprocessors:
            middleware.join(timeout=timeout)
        super().join(timeout)


__all__ = ("Uploader",)
