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
from email.message import Message
from typing import cast

import feedparser
from bs4 import BeautifulSoup, NavigableString, Tag
from feedparser import FeedParserDict
from requests import Session, Response
from requests.adapters import HTTPAdapter

from .common import YTDLWatcher
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, Platform, MediaType
from ..middlewares import Middleware


class RSSWatcher(YTDLWatcher):
    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        url: str,
        headers: dict | None = None,
        proxies: dict | None = None,
        retry_count: int = 5,
        copy: bool = False,
        **config,
    ) -> None:
        super().__init__(name, preprocessors, **config)

        self._session = Session()
        retry_adapter = HTTPAdapter(max_retries=retry_count)
        self._session.mount("http://", retry_adapter)
        self._session.mount("https://", retry_adapter)

        if headers is not None:
            self._session.headers.update(headers)  # |= doesn't work
            self._ytdl_params.setdefault("http_headers", headers)

        if proxies is not None:
            self._session.proxies |= proxies
            self._ytdl_params.setdefault("proxies", proxies)

        self.url = url
        self._copy = copy

    @classmethod
    def choose_best_watcher(
        cls, name: str, preprocessors: list[Middleware], **config
    ) -> RSSWatcher:
        """
        Chooses the best RSSWatcher for the given configuration. This will be a subclass of RSSWatcher.
        """
        url = config["url"]
        platform = Platform.from_url(url)

        match platform:
            case Platform.REDDIT:
                return RedditWatcher(name, preprocessors, **config)
            case _:
                return cls(name, preprocessors, **config)

    def close(self) -> None:
        super().close()
        self._session.close()

    def get_media_url(self, entry: FeedParserDict) -> str | None:
        """
        Gets the media url from the entry.
        This is overridable in case the media url is not in the media_thumbnail field
        """
        if (thumbnails := entry.get("media_thumbnail")) is None or len(thumbnails) == 0:
            return None  # no thumbnail, so we can't download the media

        return thumbnails[0]["url"] if len(thumbnails) > 0 else None

    def _parse_entry(
        self, entry: FeedParserDict, *, handle_if_already_handled: bool = False
    ) -> tuple[ScratchFile, MediaMetadata] | None:
        """
        Parses the entry and returns the media and metadata created from the entry
        """
        assert self.ready, "Watcher is not ready"
        assert self._file_manager is not None, "File manager is not set"

        entry_id: str = entry["id"]

        self.logger.debug(f"Parsing entry {entry_id}...")

        if not handle_if_already_handled and self.is_handled(entry_id):
            self.logger.debug(f"Entry {entry_id} is already handled, skipping...")
            return None

        # good to continue after this point

        if (media_url := self.get_media_url(entry)) is None:
            return None

        try:
            with self._session.get(
                media_url, stream=True
            ) as response:  # type: Response
                if response.status_code >= 400:
                    return None  # not successful

                mime_type = response.headers["Content-Type"]

                # the following code exists because of https://peps.python.org/pep-0594/#cgi
                message = Message()
                message["Content-Type"] = mime_type
                params = message.get_params()
                if len(params) > 1:
                    mime_type = params[0][0]

                if mime_type == "text/html":
                    # we need ol'reliable.
                    media, metadata = self._download(media_url)
                else:
                    file_extension = mimetypes.guess_extension(mime_type)

                    media = self._file_manager.get_file(file_extension=file_extension)

                    with media.open("w") as file:
                        for chunk in response.iter_content(chunk_size=8192):
                            file.write(chunk)

                    metadata = MediaMetadata(
                        media_id=entry_id,
                        platform=Platform.from_url(entry["link"]),
                        title=entry["title"],
                        description=entry["summary"],
                        tags=[tags["term"] for tags in entry["tags"]],
                        categories=[],
                        media_type=MediaType.from_mime_type(mime_type),
                        data=dict(entry),
                    )

            self.mark_handled(entry.id)
            return media, metadata
        except Exception as e:
            self.logger.error(f"Error while parsing entry {entry_id}: {e}")
            return None

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        with self._session.get(self.url) as response:
            feed = feedparser.parse(response.text)

            run = [
                parsed_entry
                for parsed_entry in [
                    self._parse_entry(entry, handle_if_already_handled=self._copy)
                    for entry in feed.entries
                ]
                if parsed_entry is not None
            ]

            if self._copy:
                self._copy = False

            return run


class RedditWatcher(RSSWatcher):
    """
    A version of RSSWatcher that is specifically for Reddit RSS urls.
    """

    # MYSQL_TYPE = "CHAR(10)"  # doesn't work with other types of posts
    SLEEP_TIME = (
        60 * 5
    )  # Reddit API advises 2 minutes, but it is unlikely something pops up every 2 minutes

    def get_media_url(self, entry: FeedParserDict) -> str | None:
        """
        Gets the media url from the entry.
        This is overridable in case the media url is not in the media_thumbnail field
        """
        maybe_super_media_url = super().get_media_url(entry)

        if maybe_super_media_url is not None:
            return maybe_super_media_url

        # default didn't work, lets try something special

        soup = BeautifulSoup(entry["summary"], "html.parser")

        link_nav_string = cast(NavigableString, soup.find(string="[link]"))

        link_parent = cast(Tag, link_nav_string.parent)

        if link_parent is None:
            return None

        return link_parent.attrs.get("href")


__all__ = ("RSSWatcher",)
