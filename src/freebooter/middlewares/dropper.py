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

import random

from .common import Middleware
from ..file_management import ScratchFile
from ..metadata import MediaMetadata


class Dropper(Middleware):
    """
    Drops a random percentage of inputted pieces of media.
    """

    def __init__(self, name: str, *, chance: float = 0.2, **config) -> None:
        """
        :param chance: The chance that a piece of media will be dropped. This is a percentage, 0-1.
        """
        super().__init__(name, **config)

        self._chance = chance

    def _process(
        self, file: ScratchFile, metadata: MediaMetadata | None
    ) -> tuple[ScratchFile, MediaMetadata | None] | None:
        if metadata is None:
            return file, metadata
        if random.random() < self._chance:
            self.logger.debug(f"Dropping {metadata.title} @ {file.path}")
            if not file.closed:
                file.close()
            return None
        return file, metadata


__all__ = ("Dropper",)
