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

from .common import ThreadWatcher
from ..file_management import ScratchFile
from ..metadata import MediaMetadata
from ..middlewares import Middleware


class Pusher(ThreadWatcher):
    """
    Periodically pushes empty media into the uploading flow. This is useful if you have a collector for counting the
    number of posts, while also having an uploader that has a rate limit to follow.
    """

    MYSQL_TYPE = None

    def __init__(self, name: str, preprocessors: list[Middleware], *, interval: int, **config) -> None:
        config.setdefault("process_if_empty", True)
        super().__init__(name, preprocessors, **config)

        self.SLEEP_TIME = interval

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        return []


__all__ = ("Pusher",)
