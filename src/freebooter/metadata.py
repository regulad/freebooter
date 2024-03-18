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

import mimetypes
from enum import Enum, auto
from logging import getLogger
from pathlib import Path
from typing import Any, Literal

import tweepy.models

logger = getLogger(__name__)


class Platform(Enum):
    UNKNOWN = auto()

    OTHER = auto()

    YOUTUBE = auto()
    TIKTOK = auto()
    INSTAGRAM = auto()
    REDDIT = auto()
    DISCORD = auto()
    TWITTER = auto()

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
    UNKNOWN = auto()

    OTHER = auto()

    PHOTO = auto()
    VIDEO = auto()

    @classmethod
    def from_twitter_type(cls, twitter_type: Literal["photo", "animated_gif", "video"]) -> MediaType:
        match twitter_type:
            case "photo" | "animated_gif":
                return cls.PHOTO
            case "video":
                return cls.VIDEO

    @classmethod
    def from_mime_type(cls, mime_type: str | None) -> MediaType:
        if mime_type is None:
            return cls.UNKNOWN
        elif mime_type.startswith("image"):
            return cls.PHOTO
        elif mime_type.startswith("video"):
            return cls.VIDEO
        else:
            logger.warning(f"Unknown media type: {mime_type}! Defaulting to UNKNOWN...")
            return cls.UNKNOWN

    @classmethod
    def from_file_path(cls, file_path: Path) -> MediaType:
        mime_type, _ = mimetypes.guess_type(file_path)
        return cls.from_mime_type(mime_type)

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

        if "mp4" in format_name:
            return cls.VIDEO

        match format_name:
            case "gif":
                return cls.PHOTO
            case "png_pipe":
                return cls.PHOTO
            case "tiff_pipe":
                return cls.PHOTO
            case "image2":
                return cls.PHOTO
            case "matroska,webm":
                return cls.VIDEO
            case _:
                logger.warning(f"Unknown media type: {format_name}! Attempting to search from file path...")
                file = Path(output_format["filename"])
                return cls.from_file_path(file)


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
        *,
        media_id: Any,
        platform: Platform = Platform.UNKNOWN,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        categories: list[str] | None = None,
        media_type: MediaType = MediaType.UNKNOWN,
        data: dict[str, Any] | None = None,
    ) -> None:
        self._id = media_id
        self._platform = platform
        self._title = title
        self._description = description
        self._tags: list[str] = tags or []
        self._categories: list[str] = categories or []
        self._type = media_type
        self._data = data or {}

    @classmethod
    def from_tweepy_status_model(cls, status: tweepy.models.Status) -> MediaMetadata:
        return cls(
            media_id=status.id_str,
            platform=Platform.TWITTER,
            title=status.text,
            description=None,
            tags=[],
            categories=[],
            media_type=MediaType.OTHER,  # tweets don't fit evenly into a category
            data=status.__getstate__(),
        )

    @classmethod
    def from_tweepy_media_model(cls, media: tweepy.models.Media) -> MediaMetadata:
        mime_type = media.image["image_type"]

        return cls(
            media_id=media.media_id_string,
            platform=Platform.TWITTER,
            title=None,
            description=None,
            tags=[],
            categories=[],
            media_type=MediaType.from_mime_type(mime_type),
            data=media.__getstate__(),
        )

    @classmethod
    def from_ytdl_info(cls, info: dict[str, Any]) -> MediaMetadata:
        return cls(
            media_id=info["id"],
            platform=Platform.from_url(info["webpage_url"]),
            title=info.get("title"),
            description=info.get("description"),
            tags=info.get("tags", []),
            categories=info.get("categories", []),
            media_type=MediaType.VIDEO,  # how tf you get a photo with ytdl
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
    def id(self) -> Any:
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
