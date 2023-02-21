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

import warnings
from io import FileIO
from logging import getLogger, Logger
from pathlib import Path
from random import choice
from string import ascii_letters
from threading import Lock
from typing import Literal, TYPE_CHECKING

from .util import WeakList

logger: Logger = getLogger(__name__)

if TYPE_CHECKING:
    FILE_IO_MODE = Literal["r", "w", "x", "a", "r+", "w+", "x+", "a+"]
else:
    FILE_IO_MODE = str


class ScratchFile:
    def __init__(
        self,
        file_manager: FileManager,
        path: Path,
        initial_bytes: bytes | None = None,
        delete_when_done: bool = True,
    ) -> None:
        self._file_manager = file_manager
        self._bytes = initial_bytes
        self._path = path
        self._delete = delete_when_done

        self._closing_lock = (
            Lock()
        )  # to prevent a deadlock since the code is hacky for closing this

        self._file: FileIO | None = None

    def __repr__(self):
        return f"ScratchFile({self._path})"

    def __str__(self):
        return str(self._path)

    @property
    def exists(self) -> bool:
        return self._path.exists()

    @property
    def path(self) -> Path:
        return self._path

    def _get_file(self, mode: FILE_IO_MODE = "w+") -> FileIO:
        fileio = FileIO(self._path, mode)
        if self._bytes is not None:
            fileio.write(self._bytes)
        fileio.seek(0)
        return fileio

    def open(self, mode: FILE_IO_MODE = "r+") -> FileIO:
        """
        Opens the file and returns a FileIO object. You shouldn't open this file yourself, as the ScratchFile takes care of the lifecycle.
        :return:
        """
        if self._file is None or self._file.closed:
            self._file = self._get_file(mode)
        elif self._file.mode != mode:
            self._file.close()
            self._file = self._get_file(mode)
        return self._file

    def __enter__(self) -> ScratchFile:
        return self

    def __del__(self) -> None:
        if not self.closed:
            warnings.warn(
                "ScratchFile objects should be closed manually!", ResourceWarning
            )
            self.close()

    @property
    def closed(self) -> bool:
        return not self._path.exists() and (self._file is None or self._file.closed)

    def close(self) -> None:
        with self._closing_lock:
            # ScratchFile would be a context manager, but it's not possible to use it as one because
            # it's not guaranteed to be used in a thread-safe manner.

            # If possible, I would rather have ScratchFile be an inner class of FileManager, but that is not possible in
            # the Java-like manner I prefer because of the way Python works.
            with self._file_manager._lock:  # noqa
                self._file_manager._files.remove(self)  # noqa  # i know

            if self._file is not None:
                self._file.close()
            if self._delete:
                self._path.unlink(missing_ok=True)

            assert self.closed, "File was not closed correctly!"

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class FileManager:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

        if not self._directory.exists():
            self._directory.mkdir()

        self._files: WeakList = WeakList()

        self._lock = Lock()

        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        assert not self.closed, "Close was called more than once!"
        for file in self._files.copy():  # changes in size
            file.close()
        for file in self.directory.iterdir():
            logger.warning(
                f"Deleting file {file} because it was not deleted automatically!"
            )
            file.unlink()
        self._closed = True

    def __del__(self):
        if not self.closed:
            warnings.warn(
                "FileManager objects should be closed manually!", ResourceWarning
            )
            self.close()

    @property
    def directory(self) -> Path:
        return self._directory

    @staticmethod
    def get_file_ident() -> str:
        return "".join(choice(ascii_letters) for _ in range(15))

    def get_file(
        self,
        *,
        file_extension: str | None = None,
        initial_bytes: bytes | None = None,
        file_name: str | Path | None = None,
    ) -> ScratchFile:
        """
        Returns an empty ScratchFile object with a random name and the given file extension.
        This class is thread-safe.
        :param file_extension: A file extension to use for the file.
        :param initial_bytes: Bytes that will be in the file when it is created. If unspecified, the file will be empty when opened.
        :param file_name: The name of the file. If unspecified, a random name will be used.
        :return: A ScratchFile object. That can be used.
        """
        with self._lock:
            file_name_chosen: bool = file_name is not None

            if file_name is None:
                assert file_extension is not None, "File extension must be specified"
                assert (
                    file_extension.startswith(".") and not file_extension.endswith(".")
                ) or len(file_extension) == 0, "File extension must start with a period"
                file_name = self.get_file_ident() + file_extension

            file_name = (
                Path(file_name) if not isinstance(file_name, Path) else file_name
            )

            if not file_name.is_absolute():
                file_name = self._directory / file_name

            assert file_name is not None, "Could not find a file name!"

            logger.debug(f"Allocating ScratchFile at {file_name}")

            if file_name.exists() and not file_name_chosen:
                # If a ScratchFile is allocated but doesn't exist, it will cause unexpected behavior.
                # If it has a name chosen, then it is expected that something like YoutubeDL has already written to it,
                #   and it is safe to use.
                return self.get_file(
                    file_extension=file_extension,
                    initial_bytes=initial_bytes,
                    file_name=None,
                )
                # Handing over a file that exists could result in unexpected behavior.
            else:
                scratch_file = ScratchFile(
                    self, file_name, initial_bytes
                )  # Good to go!
                self._files.append(scratch_file)
                return scratch_file


__all__ = ("FileManager", "ScratchFile")
