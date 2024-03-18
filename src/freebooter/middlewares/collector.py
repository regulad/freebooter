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

from concurrent.futures import Future
from queue import Queue
from threading import Lock
from typing import cast

from .common import *
from ..file_management import ScratchFile
from ..metadata import MediaMetadata
from ..types import UploadCallback


class Collector(Middleware):
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
        self._lock = Lock()  # need to lock to prevent stuff from being "stolen" by other threads

    def close(self) -> None:
        """
        Closes the middleware.
        """
        self.flush()
        self._media.join()
        super().close()

    def flush(self) -> None:
        self.logger.debug("Flushing collector queue...")

        callback: UploadCallback | None = self._prepare_kwargs.get("callback")

        if callback is None:
            raise RuntimeError("Collector middleware requires a callback to be set.")

        while not self._media.empty():
            split_medias: list[tuple[ScratchFile, MediaMetadata]] = []

            while len(split_medias) < self._count and not self._media.empty():
                got_media = self._media.get()
                file, metadata = got_media
                self.logger.debug(f"Flushing media {metadata.id}.")
                split_medias.append(got_media)

            self.logger.info(f"Sending {len(split_medias)} media(s) out-of-lifecycle...")

            def _affirm_result(done_future: Future[list[tuple[ScratchFile, MediaMetadata | None]]]) -> None:
                try:
                    result = done_future.result(timeout=0)
                except TimeoutError:
                    result = None

                if result is None:
                    self.logger.error(f"{self.name} upload callback failed!")
                else:
                    self.logger.debug(f"{self.name} upload callback finished.")

            # needs to be cast because mypy doesn't understand that the second element of the tuple being none doesn't
            # break the type of the union
            fut = callback(cast("list[tuple[ScratchFile, MediaMetadata | None]]", split_medias))

            fut.add_done_callback(lambda _: self._media.task_done())
            fut.add_done_callback(_affirm_result)

    def process_many(
        self, medias: list[tuple[ScratchFile, MediaMetadata | None]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        mut_medias = medias.copy()  # safe to mutate this list because it's a copy
        with self._lock:
            for media_pair in medias:
                file, metadata = media_pair

                if metadata is None:
                    # Don't remove it from the list. Let it be closed normally.
                    continue

                self.logger.debug(f"Collecting media {metadata.id}.")

                processed_pair = self._process(file, metadata)

                if processed_pair is not None:
                    processed_file, processed_metadata = processed_pair
                    if processed_metadata is None:
                        mut_medias[mut_medias.index(media_pair)] = processed_pair
                    else:
                        self._media.put(processed_pair)  # type: ignore  # mypy is wrong, the second element of the tuple can never be none
                        mut_medias.remove(media_pair)

            self.logger.debug(f"Queue is {self._media.qsize()} long.")

            while len(mut_medias) < self._count and not self._media.empty():
                got_media = self._media.get()
                file, metadata = got_media
                self.logger.debug(f"Releasing media {metadata.id}.")
                mut_medias.append(got_media)
                self._media.task_done()

            if not self._media.empty() and len(medias) > self._count:
                # We need to split the post into multiple posts.
                # If we let it collect on its own, we would have medias that would leak into the next post.
                # This is done by releasing the media that we have collected so far.
                # The rest of the media will be released in the next call to this method.
                self.logger.debug("Flushing out remaining posts...")

                self.flush()

            return mut_medias


__all__ = ("Collector",)
