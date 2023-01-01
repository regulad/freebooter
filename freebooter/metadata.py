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
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class Platform(Enum):
    YOUTUBE = auto()
    TIKTOK = auto()  # for future use
    INSTAGRAM = auto()  # for future use

    @classmethod
    def from_url(cls, url: str) -> "Platform":
        if "youtube.com" in url:
            return cls.YOUTUBE
        elif "tiktok.com" in url:
            return cls.TIKTOK
        elif "instagram.com" in url:
            return cls.INSTAGRAM
        else:
            raise ValueError("Unknown platform")

    @classmethod
    def find_from_out_channel(cls, channel_parameter: str) -> "Platform":
        if channel_parameter.startswith("client_secret_"):
            return cls.YOUTUBE
        else:
            raise ValueError(f"Invalid channel parameter: {channel_parameter}")

    @classmethod
    def find_from_in_channel(cls, channel_parameter) -> "Platform":
        if channel_parameter.startswith("UC") and len(channel_parameter) == 24:
            return cls.YOUTUBE
        # in the future there will be checks for TikTok and Instagram Reels here
        else:
            raise ValueError(f"Invalid channel parameter: {channel_parameter}")


class MediaMetadata:
    __slots__ = (
        "_id",
        "_platform",
        "_title",
        "_description",
        "_tags",
        "_categories",
        "_data"
    )

    def __init__(
            self,
            media_id: str,
            platform: Platform,
            title: str | None,
            description: str,
            tags: list[str],
            categories: list[str],
            data: "dict[str, Any] | None" = None,
    ) -> None:
        self._id: str = media_id
        self._platform: Platform = platform
        self._title: str | None = title
        self._description: str = description
        self._tags: list[str] = tags
        self._categories: list[str] = categories
        self._data: "dict[str, Any]" = data or {}

    @classmethod
    def from_ytdl_info(cls, info: "dict[str, Any]") -> "MediaMetadata":
        return cls(
            info["id"],
            Platform.from_url(info["webpage_url"]),
            info["title"],
            info["description"],
            info["tags"],
            info["categories"],
            data=info,
        )

    @property
    def data(self) -> "dict[str, Any]":
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
    def description(self) -> str:
        return self._description

    @property
    def tags(self) -> list[str]:
        return self._tags

    @property
    def categories(self) -> list[str]:
        return self._categories


__all__: tuple[str] = (
    "Platform",
    "MediaMetadata"
)
