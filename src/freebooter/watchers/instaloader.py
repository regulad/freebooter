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

from threading import Event
from typing import Any, Generator

from instaloader import Instaloader, Profile, Post, NodeIterator
from mariadb import ConnectionPool
from requests import Session

from .common import Watcher, UploadCallback
from ..file_management import ScratchFile, FileManager
from ..metadata import MediaMetadata, MediaType, Platform
from ..middlewares import Middleware


class InstaloaderWatcher(Watcher):
    SLEEP_TIME = 60 * 30  # 30 minutes

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        # Instaloader configuration
        instaloader_kwargs: dict[str, Any] | None = None,
        proxies: dict[str, str] | None = None,
        # Watcher Configuration
        backtrack: bool = False,
        copy: bool = False,
        # Username to watch
        username: str | None = None,
        userid: int | None = None,
        **config,
    ) -> None:
        super().__init__(name, preprocessors, **config)

        self._copy = copy
        self._backtrack = backtrack

        self._iloader_kwargs: dict[str, Any] = instaloader_kwargs or {}
        self._proxies: dict[str, str] = proxies or {}
        self._loader: Instaloader | None = None
        self._profile: Profile | None = None

        if username is None and userid is None:
            raise ValueError("Either username or userid must be specified!")

        self._username = username
        self._userid = userid

    @property
    def _session(self) -> Session:
        assert self._loader is not None, "InstaloaderWatcher not prepared!"
        return self._loader.context._session  # noqa

    def prepare(
        self,
        shutdown_event: Event,
        callback: UploadCallback,
        pool: ConnectionPool,
        file_manager: FileManager,
    ) -> None:
        super().prepare(shutdown_event, callback, pool, file_manager)

        assert self._file_manager is not None, "File manager was not set!"

        self._iloader_kwargs.setdefault(
            "quiet", True
        )  # doesn't log to a logger, prints to stdout
        self._iloader_kwargs.setdefault(
            "dirname_pattern", str(self._file_manager.directory)
        )
        self._iloader_kwargs.setdefault("filename_pattern", "{target}")
        self._iloader_kwargs.setdefault("save_metadata", False)
        self._loader = Instaloader(**self._iloader_kwargs)
        self._session.proxies |= self._proxies

        if self._username is not None:
            self._profile = Profile.from_username(self._loader.context, self._username)
        elif self._userid is not None:
            self._profile = Profile.from_id(self._loader.context, self._userid)

        assert self._profile is not None, "A profile was not found!"

    def _check_for_uploads_generator(
        self,
    ) -> Generator[tuple[ScratchFile, MediaMetadata], None, None]:
        assert self._profile is not None, "A profile was not found!"
        assert self._loader is not None, "Instaloader was not initialized!"
        assert self._file_manager is not None, "File manager was not initialized!"

        posts: NodeIterator[Post] = self._profile.get_posts()
        # by default returns most recent to oldest

        posts_final: NodeIterator[Post] | list[Post]
        if self._backtrack:
            posts_final = list(posts)
            posts_final.reverse()
        else:
            # we only need the newest post
            posts_final = [posts.__next__()]

        del posts  # free up memory

        for post in posts_final:
            if not self._copy and self.is_handled(post.shortcode):
                continue

            file_ident = self._file_manager.get_file_ident()

            self._loader.download_post(post, file_ident)

            final_filename = (self._file_manager.directory / file_ident).with_suffix(
                ".mp4" if post.is_video else ".jpg"
            )

            file = self._file_manager.get_file(file_name=final_filename)

            metadata = MediaMetadata(
                media_id=post.shortcode,
                platform=Platform.INSTAGRAM,
                title=post.caption,
                description=post.caption,
                tags=post.caption_hashtags,
                categories=[],
                media_type=MediaType.VIDEO if post.is_video else MediaType.PHOTO,
                data=post._node if hasattr(post, "_node") else None,  # noqa
            )

            yield file, metadata

            self.mark_handled(post.shortcode)

        if self._copy:
            self._copy = False

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        return list(self._check_for_uploads_generator())
