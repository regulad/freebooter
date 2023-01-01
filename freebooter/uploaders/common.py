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
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..file_management import ScratchFile
    from ..metadata import MediaMetadata


class Uploader:
    def __init__(self) -> None:
        self._lock: "Lock" = Lock()

    def handle_upload(self, file: "ScratchFile", metadata: "MediaMetadata") -> "MediaMetadata | None":
        raise NotImplementedError

    def upload(self, file: "ScratchFile", metadata: "MediaMetadata") -> "MediaMetadata | None":
        with self._lock:
            return self.handle_upload(file, metadata)

    def close(self) -> None:
        pass


__all__: tuple[str] = (
    "Uploader",
)
