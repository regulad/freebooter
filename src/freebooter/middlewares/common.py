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

from abc import ABCMeta
from logging import Logger, getLogger
from threading import Thread, Event

from ..file_management import ScratchFile, FileManager
from ..metadata import MediaMetadata


class Middleware(Thread, metaclass=ABCMeta):
    """
    A middleware is a class that can be used to modify the media that is downloaded by freebooter.
    The process method may be called concurrently, so it must be thread-safe.
    """

    BACKGROUND_TASK_INTERVAL_SECONDS = 60

    def __init__(self, name: str, **config) -> None:
        super().__init__(
            name=f"{self.__class__.__name__}-{name.title().replace(' ', '-')}"
        )

        self.config = config

        self._file_manager: FileManager | None = None
        self._shutdown_event: Event | None = None

    def background_task(self) -> None:
        """
        Override this method to implement a background task, like keeping a connection alive.
        """
        pass

    def run(self) -> None:
        assert self.ready, "Middleware is not ready!"
        assert self._shutdown_event is not None, "Middleware is not ready!"

        while not self._shutdown_event.is_set():
            self.background_task()
            self._shutdown_event.wait(self.BACKGROUND_TASK_INTERVAL_SECONDS)

    @property
    def logger(self) -> Logger:
        return getLogger(self.name)

    @property
    def ready(self) -> bool:
        return self._file_manager is not None and self._shutdown_event is not None

    def close(self) -> None:
        """
        Override this method to implement a close method. Will be called when the middleware is shutting down.
        """
        pass

    def prepare(self, shutdown_event: Event, file_manager: FileManager):
        assert not self.ready, "Middleware is already ready."

        self._shutdown_event = shutdown_event
        self._file_manager = file_manager

        assert self.ready, "Middleware failed to prepare."

    def _process(
        self, file: ScratchFile, metadata: MediaMetadata
    ) -> tuple[ScratchFile, MediaMetadata] | None:
        """
        Processes some media.
        This is not guaranteed to be called on the same thread as the Middleware itself, and probably will not be.
        """
        raise NotImplementedError

    def process_one(
        self, file: ScratchFile, metadata: MediaMetadata
    ) -> tuple[ScratchFile, MediaMetadata] | None:
        assert self.ready, "Middleware is not ready."
        return self._process(file, metadata)

    def process_many(
        self, media: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata]]:
        assert self.ready, "Middleware is not ready."
        return [
            pair
            for pair in [self.process_one(file, metadata) for file, metadata in media]
            if pair is not None
        ]


__all__ = ("Middleware",)