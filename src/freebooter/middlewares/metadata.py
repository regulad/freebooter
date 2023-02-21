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

import typing

from .common import *
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, Platform


class MissingType:
    """
    A singleton class that represents a missing value. This is used in cases where None is a valid value that is different from passing nothing.
    """

    def __init__(self) -> None:
        if globals().get("Missing", None) is not None:
            raise RuntimeError("Cannot create another instance of MISSING!")

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(None)


Missing = MissingType()


class MetadataModifier(Middleware):
    """
    Modifies the MediaMetadata of a passed file.
    """

    def __init__(
        self,
        name: str,
        *,
        platform: str | MissingType = Missing,
        title: str | None | MissingType = Missing,
        description: str | None | MissingType = Missing,
        tags: list[str] | None | MissingType = Missing,
        categories: list[str] | None | MissingType = Missing,
        **config,
    ) -> None:
        super().__init__(name, **config)

        self._platform = platform
        self._title = title
        self._description = description
        self._tags = tags
        self._categories = categories

        if not any(
            [
                self._platform is not Missing,
                self._title is not Missing,
                self._description is not Missing,
                self._tags is not Missing,
                self._categories is not Missing,
            ]
        ):
            raise ValueError("No metadata to modify!")

    @typing.no_type_check  # this shreds mypy fsr
    def _process(
        self, file: ScratchFile, metadata: MediaMetadata
    ) -> tuple[ScratchFile, MediaMetadata] | None:
        metadata = MediaMetadata(
            media_id=metadata.id,
            platform=Platform[self._platform.lower()]
            if self._platform is not Missing
            else metadata.platform,
            title=self._title if self._title is not Missing else metadata.title,
            description=self._description
            if self._description is not Missing
            else metadata.description,
            tags=(self._tags or []) if self._tags is not Missing else metadata.tags,
            categories=(self._categories or [])
            if self._categories is not Missing
            else metadata.categories,
            media_type=metadata.type,
            data=metadata.data,
        )

        return file, metadata


__all__ = ("MetadataModifier",)
