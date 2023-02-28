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
from threading import Lock
from typing import ClassVar

from .common import Uploader
from ..file_management import ScratchFile
from ..metadata import MediaMetadata
from ..middlewares import Middleware


class LocalMediaStorage(Uploader):
    """
    "Uploads" media by saving it to a local directory.
    """

    glock: ClassVar[Lock] = Lock()

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

    def upload(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        metadatas: list[tuple[ScratchFile, MediaMetadata | None]] = []
        for file, metadata in medias:
            potential_path = self._directory.joinpath(file.path.name)
            while potential_path.exists():
                potential_path = potential_path.with_name(f"{potential_path.stem}_1{potential_path.suffix}")

            copyfile(file.path, potential_path)
            self.logger.debug(f"Saved {file.path.name} to {self._directory}")

            ret_metadata = MediaMetadata(
                media_id=str(potential_path.resolve()),
            )

            metadatas.append((file, ret_metadata))
            # a generator would be better here but due to the nasty thready nature of the program, it's not possible to
        return metadatas


__all__ = ("LocalMediaStorage",)
