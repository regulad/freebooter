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

from queue import Queue
from threading import Lock

from .common import *
from ..file_management import ScratchFile
from ..metadata import MediaMetadata


class MediaCollector(Middleware):
    """
    This middleware collects media and then releases it when enough have been accumulated.
    """

    def __init__(self, name: str, *, count: int = 1, **config) -> None:
        """
        :param count: The number of media to collect before releasing them. If a post has more than this number of media,
            then the post will be split into multiple posts.
        """
        super().__init__(name, **config)

        self._count = count

        self._media: Queue[tuple[ScratchFile, MediaMetadata]] = Queue()
        self._lock = (
            Lock()
        )  # need to lock to prevent stuff from being "stolen" by other threads

    def close(self) -> None:
        """
        Closes the middleware.
        """
        while not self._media.empty():
            got_media = self._media.get()
            self.logger.debug(f"Releasing media {got_media[1].id} ON CLOSE.")
            got_media[0].close()

    def _process(
        self, file: ScratchFile, metadata: MediaMetadata
    ) -> tuple[ScratchFile, MediaMetadata] | None:
        """
        Collects the media and releases it when enough have been collected. no-op.
        """
        return file, metadata  # no-op

    def process_many(
        self, media: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata]]:
        with self._lock:
            for media_pair in media:
                self.logger.debug(f"Collecting media {media_pair[1].id}.")
                self._media.put(media_pair)

            returned_medias: list[tuple[ScratchFile, MediaMetadata]] = []

            self.logger.debug(f"Queue is {self._media.qsize()} long.")

            while len(returned_medias) < self._count and not self._media.empty():
                got_media = self._media.get()
                self.logger.debug(f"Releasing media {got_media[1].id}.")
                returned_medias.append(got_media)

            return returned_medias


__all__ = ("MediaCollector",)
