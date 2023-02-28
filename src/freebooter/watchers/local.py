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

from pathlib import Path
from shutil import copyfile
from typing import Generator

import ffmpeg

from .common import ThreadWatcher
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, MediaType, Platform
from ..middlewares import Middleware


class LocalMediaLoader(ThreadWatcher):
    """
    Loads media from a directory on the local file system.
    """

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        path: str,
        **config,
    ) -> None:
        directory_path = Path(path)

        if not directory_path.is_absolute():
            directory_path = directory_path.absolute()

        if not directory_path.exists():
            directory_path.mkdir(parents=True)

        if not directory_path.is_dir():
            raise ValueError(f"{directory_path} is not a directory!")

        self._directory = directory_path

        super().__init__(name, preprocessors, **config)

    def _check_in_folder(
        self, folder: Path, *, handle_if_already_handled: bool = False
    ) -> Generator[tuple[ScratchFile, MediaMetadata], None, None]:
        assert self._file_manager is not None, "File manager not set!"
        assert folder.is_dir(), f"{folder} is not a directory!"

        for file in folder.iterdir():
            if file.is_dir():
                yield from self._check_in_folder(file, handle_if_already_handled=handle_if_already_handled)
            elif file.name != ".DS_Store":  # macos ong
                if not handle_if_already_handled and self.is_handled(file.name):
                    continue

                scratch_file = self._file_manager.get_file(file_extension=file.suffix)

                copyfile(file, scratch_file.path)

                data: dict | None
                media_type: MediaType
                try:
                    ffprobe_out = ffmpeg.probe(str(scratch_file.path))
                    media_type = MediaType.from_ffprobe_output(ffprobe_out)
                    data = ffprobe_out
                except ffmpeg.Error:
                    data = None
                    media_type = MediaType.from_file_path(file)

                metadata = MediaMetadata(
                    media_id=file.stem,
                    platform=Platform.OTHER,
                    title=file.stem,
                    description="",
                    tags=[],
                    categories=[],
                    media_type=media_type,
                    data=data,
                )

                self.mark_handled(file.name)

                yield scratch_file, metadata

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        run = list(self._check_in_folder(self._directory, handle_if_already_handled=self._copy))

        return run


__all__ = ("LocalMediaLoader",)
