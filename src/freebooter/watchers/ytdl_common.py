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
from os import sep
from pathlib import Path
from threading import Event

from mariadb import ConnectionPool
from yt_dlp import YoutubeDL

from .common import Watcher, UploadCallback
from ..file_management import ScratchFile, FileManager
from ..metadata import MediaMetadata
from ..middlewares import Middleware


class YTDLWatcher(Watcher, metaclass=ABCMeta):
    """
    This watcher uses youtube-dl to download videos from a channel.
    """

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        ytdl_params: dict | None = None,
        **config,
    ) -> None:
        """
        :param ytdl_params: Parameters to pass to the youtube-dl downloader constructor (see youtube_dl.YoutubeDL)
        """
        if ytdl_params is None:
            ytdl_params = {}

        assert ytdl_params is not None, "ytdl_params must not be None"  # for mypy

        super().__init__(name=name, preprocessors=preprocessors, **config)

        self._ytdl_params: dict = ytdl_params

        self._ytdl_params.setdefault("logger", self.logger)

        self._downloader: YoutubeDL | None = None

    def _download(self, query: str) -> tuple[ScratchFile, MediaMetadata]:
        assert self._downloader is not None, "Downloader not initialized"
        assert self._file_manager is not None, "File manager not initialized"

        self.logger.debug(f'Downloading video with query "{query}"...')

        info: dict = self._downloader.extract_info(query, download=True)

        filename: str = self._downloader.prepare_filename(info)

        filepath = Path(filename)

        scratch_file = self._file_manager.get_file(file_name=filepath)

        metadata = MediaMetadata.from_ytdl_info(info)

        return scratch_file, metadata

    def close(self) -> None:
        del self._downloader  # ytdl does some closing but not openly
        self._downloader = None

    def prepare(
        self,
        shutdown_event: Event,
        callback: UploadCallback,
        pool: ConnectionPool,
        file_manager: FileManager,
    ) -> None:
        super().prepare(shutdown_event, callback, pool, file_manager)

        assert self._downloader is None, "Downloader already initialized"
        assert self._file_manager is not None, "File manager not initialized"

        self._ytdl_params.setdefault(
            "outtmpl", f"{self._file_manager.directory}{sep}%(id)s.%(ext)s"
        )

        self._downloader = YoutubeDL(self._ytdl_params)


__all__ = ("YTDLWatcher",)
