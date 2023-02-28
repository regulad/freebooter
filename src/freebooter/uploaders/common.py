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
from logging import getLogger, Logger
from threading import Event, Lock
from typing import cast, ClassVar

from ..file_management import ScratchFile, FileManager
from ..metadata import MediaMetadata
from ..middlewares import Middleware


class Uploader(metaclass=ABCMeta):
    """
    Base class for all uploaders. Uploaders are responsible for uploading media to social media platforms.
    They are a thread to allow the execution of background tasks.
    """

    # This is necessary to reduce the chance of too many connections to the internet being opened in parallel and
    # causing a timeout error, connection ended error, or other similar error.
    glock: ClassVar[Lock] = Lock()

    def __init__(
        self, name: str, preprocessors: list[Middleware], *, run_concurrently: bool = False, **config
    ) -> None:
        self.name = f"{self.__class__.__name__}-{name.title().replace(' ', '-')}"

        self._shutdown_event: Event | None = None
        self._file_manager: FileManager | None = None
        self._run_concurrently = run_concurrently
        self.preprocessors = preprocessors

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

    def prepare(self, **kwargs) -> None:
        assert not self.ready, "Uploader is already ready!"

        self.logger.debug(f"Preparing uploader {self.name}...")

        self._shutdown_event = kwargs["shutdown_event"]
        self._file_manager = kwargs["file_manager"]

        for middleware in self.preprocessors:
            middleware.prepare(**kwargs)

        assert self.ready, "Uploader failed to prepare."

    def upload(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        raise NotImplementedError

    def upload_and_preprocess(
        self, medias: list[tuple[ScratchFile, MediaMetadata | None]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        for middleware in self.preprocessors:
            medias = middleware.process_many(medias)
        try:
            uploaded: list[tuple[ScratchFile, MediaMetadata | None]] = []

            # Add the "real" uploads
            valid_medias: list[tuple[ScratchFile, MediaMetadata]] = cast(
                "list[tuple[ScratchFile, MediaMetadata]]",
                # mypy also fucks up this cast
                [media for media in medias if media[1] is not None],
            )

            if valid_medias:
                if self._run_concurrently:
                    real_uploads = self.upload(valid_medias)
                else:
                    with self.glock:
                        real_uploads = self.upload(valid_medias)

                uploaded.extend(real_uploads)

            # Add the leftovers
            uploaded.extend(media for media in medias if media[1] is None)

            return uploaded
        except Exception as e:
            self.logger.exception(f"Failed to upload media: {e}")
            return []

    def close(self) -> None:
        self.logger.debug(f"Closing uploader {self.name}...")

        for middleware in self.preprocessors:
            middleware.close()


__all__ = ("Uploader",)
