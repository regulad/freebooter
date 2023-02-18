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

from enum import Enum, auto
from logging import getLogger
from typing import Any

logger = getLogger(__name__)


class Platform(Enum):
    YOUTUBE = auto()
    TIKTOK = auto()
    INSTAGRAM = auto()
    REDDIT = auto()

    @classmethod
    def from_url(cls, url: str) -> Platform:
        if "youtube.com" in url:
            return cls.YOUTUBE
        elif "tiktok.com" in url:
            return cls.TIKTOK
        elif "instagram.com" in url:
            return cls.INSTAGRAM
        elif "reddit.com" in url:
            return cls.REDDIT
        else:
            raise ValueError("Unknown platform")


class MediaType(Enum):
    PHOTO = auto()
    VIDEO = auto()

    @classmethod
    def from_mime_type(cls, mime_type: str) -> MediaType:
        if mime_type.startswith("image"):
            return cls.PHOTO
        elif mime_type.startswith("video"):
            return cls.VIDEO
        else:
            raise ValueError("Unknown media type")

    @classmethod
    def from_ffprobe_output(cls, output: dict) -> MediaType:
        """
        Get the media type from the output of ffprobe.
        example code:
        ```
        import ffmpeg
        output = ffmpeg.probe("path/to/file")
        media_type = MediaType.from_ffprobe_output(output)
        ```
        :param output: The output of ffprobe.
        :return: The media type.
        """
        output_format = output["format"]
        format_name = output_format["format_name"]
        match format_name:
            case "image2":
                return cls.PHOTO
            case "matroska,webm":
                return cls.VIDEO
            case _:
                logger.info(f"Unknown media type: {format_name}")
                return cls.VIDEO


class MediaMetadata:
    __slots__ = (
        "_id",
        "_platform",
        "_title",
        "_description",
        "_tags",
        "_categories",
        "_data",
        "_type",
    )

    def __init__(
        self,
        media_id: str,
        platform: Platform,
        title: str | None,
        description: str | None,
        tags: list[str],
        categories: list[str],
        type_: MediaType,
        data: dict[str, Any] | None = None,
    ) -> None:
        self._id = media_id
        self._platform = platform
        self._title = title
        self._description = description
        self._tags = tags
        self._categories = categories
        self._type = type_
        self._data = data or {}

    @classmethod
    def from_ytdl_info(cls, info: dict[str, Any]) -> MediaMetadata:
        return cls(
            info["id"],
            Platform.from_url(info["webpage_url"]),
            info.get("title"),
            info.get("description"),
            info.get("tags", []),
            info.get("categories", []),
            MediaType.VIDEO,  # how tf you get a photo with ytdl
            data=info,
        )

    @property
    def data(self) -> dict[str, Any]:
        """
        This can be any data from the source platform that you want to keep track of.
        :return: The data dictionary. This is capable of being JSON serialized.
        """
        return self._data

    @property
    def id(self) -> str:
        return self._id

    @property
    def platform(self) -> Platform:
        return self._platform

    @property
    def title(self) -> str | None:
        return self._title

    @property
    def description(self) -> str | None:
        return self._description

    @property
    def tags(self) -> list[str]:
        return self._tags

    @property
    def categories(self) -> list[str]:
        return self._categories

    @property
    def type(self) -> MediaType:
        return self._type

    def __repr__(self) -> str:
        return f"<MediaMetadata id={self.id} platform={self.platform} title={self.title!r} description={self.description!r} tags={self.tags!r} categories={self.categories!r}>"

    def __str__(self) -> str:
        return f"MediaMetadata(id={self.id}, platform={self.platform}, title={self.title!r}, description={self.description!r}, tags={self.tags!r}, categories={self.categories!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MediaMetadata):
            return NotImplemented
        return self.id == other.id and self.platform == other.platform

    def __hash__(self) -> int:
        return hash((self.id, self.platform))


__all__ = ("Platform", "MediaMetadata", "MediaType")
