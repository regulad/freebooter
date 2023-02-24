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
from typing import Any
from string import Formatter

from .common import *
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, Platform, MediaType


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
        title: str | list[str] | None | MissingType = Missing,
        description: str | list[str] | None | MissingType = Missing,
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

    @staticmethod
    def format_description(string: str, tags: list[str], categories: list[str]) -> str:
        formatter = Formatter()
        # in the future, this may not allow the access of dunder methods/attributes
        # but at a small scale it's not a big deal

        randtags_list = tags.copy()
        random.shuffle(randtags_list)
        randtags = " ".join(randtags_list[:10])

        randhtags_list = [f"#{tag}" for tag in tags]
        random.shuffle(randhtags_list)
        randhtags = " ".join(randhtags_list[:10])

        randcategory = random.choice(categories)

        return formatter.format(
            string,
            tags=tags,
            randtags=randtags,
            randhtags=randhtags,
            categories=categories,
            randcategory=randcategory,
        )

    def _process(
        self, file: ScratchFile, metadata: MediaMetadata | None
    ) -> tuple[ScratchFile, MediaMetadata | None] | None:
        if metadata is None:
            return file, metadata

        media_id: str = metadata.id
        platform: Platform = metadata.platform
        title: str | None = metadata.title
        description: str | None = metadata.description
        tags: list[str] = metadata.tags
        categories: list[str] = metadata.categories
        media_type: MediaType = metadata.type
        data: dict[str, Any] = metadata.data

        if not isinstance(self._platform, MissingType):
            platform = Platform[self._platform.lower()]

        if not isinstance(self._tags, MissingType):
            tags = self._tags or []

        if not isinstance(self._categories, MissingType):
            categories = self._categories or []

        if not isinstance(self._title, MissingType):
            if isinstance(self._title, list):
                title = "\n".join(self._title)
            else:
                title = self._title

            if isinstance(title, str):
                title = self.format_description(title, tags, categories)

        if not isinstance(self._description, MissingType):
            if isinstance(self._description, list):
                description = "\n".join(self._description)
            else:
                description = self._description

            if isinstance(description, str):
                description = self.format_description(description, tags, categories)

        # cannot modify media_id, media_type, or data

        metadata = MediaMetadata(
            media_id=media_id,
            platform=platform,
            title=title,
            description=description,
            tags=tags,
            categories=categories,
            media_type=media_type,
            data=data,
        )

        return file, metadata


__all__ = ("MetadataModifier",)
