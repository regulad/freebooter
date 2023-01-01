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

# TODO: make this it's own package


from io import FileIO
from logging import getLogger
from pathlib import Path
from random import choice
from string import ascii_letters
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger

logger: "Logger" = getLogger(__name__)


class ScratchFile:
    def __init__(self, path: "Path", initial_bytes: bytes | None = None, should_delete: bool = True) -> None:
        self._bytes: bytes = initial_bytes
        self._path: Path = path
        self._file: FileIO | None = None
        self._delete: bool = should_delete

    def __str__(self):
        return str(self._path)

    @property
    def exists(self) -> bool:
        return self._path.exists()

    @property
    def path(self) -> "Path":
        return self._path

    def open(self, mode: str = "wb") -> "FileIO":
        """
        Opens the file and returns a FileIO object. You shouldn't open this file yourself, as the ScratchFile takes care of the lifecycle.
        :return:
        """
        if self._file is None:
            self._file = self._path.open(mode)
        return self._file

    def __enter__(self) -> "ScratchFile":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._file is not None:
            self._file.close()
        if self._delete:
            self._path.unlink(missing_ok=True)


class FileManager:
    def __init__(self, directory: "Path") -> None:
        self._directory: "Path" = directory

        if not self._directory.exists():
            self._directory.mkdir()

        self._lock: "Lock" = Lock()

    @property
    def directory(self) -> "Path":
        return self._directory

    def get_file(self, *, file_extension: str = None, initial_bytes: bytes | None = None,
                 file_name: str | Path = None) -> ScratchFile:
        """
        Returns an empty ScratchFile object with a random name and the given file extension.
        This class is thread-safe.
        :param file_extension: A file extension to use for the file.
        :param initial_bytes: Bytes that will be in the file when it is created. If unspecified, the file will be empty when opened.
        :param file_name: The name of the file. If unspecified, a random name will be used.
        :return: A ScratchFile object. That can be used.
        """
        assert file_extension is not None or file_name is not None, \
            "You must specify either a file extension or a file name"

        if file_extension is not None:
            assert (file_extension.startswith(".") and not file_extension.endswith(".")) or \
                   len(file_extension) == 0, "File extension must start with a period"

        file_name_chosen: bool = file_name is not None
        file_name_absolute: bool = file_name_chosen and isinstance(file_name, Path) and file_name.is_absolute()

        file_name: str | Path = file_name or \
                                f"{self.directory}{''.join(choice(ascii_letters) for _ in range(15))}{file_extension}"
        path: "Path" = self._directory.joinpath(file_name) if not file_name_absolute else file_name

        logger.debug(f"Allocating ScratchFile at {path}")

        if path.exists() and not file_name_chosen:
            # If a ScratchFile is allocated but doesn't exist, it will cause unexpected behavior.
            # If it has a name chosen, then it is expected that something like YoutubeDL has already written to it,
            #   and it is safe to use.
            return self.get_file(file_extension=file_extension, initial_bytes=initial_bytes, file_name=None)
            # Handing over a file that exists could result in unexpected behavior.
        else:
            return ScratchFile(path, initial_bytes)  # Good to go!


__all__: tuple[str] = (
    "FileManager",
    "ScratchFile"
)
