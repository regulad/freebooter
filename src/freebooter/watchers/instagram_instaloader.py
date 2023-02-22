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

from os import environ
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Generator

from instaloader import (
    Instaloader,
    Profile,
    Post,
    NodeIterator,
    ProfileNotExistsException,
)
from mariadb import ConnectionPool
from requests import Session

from .common import Watcher, UploadCallback
from ..file_management import ScratchFile, FileManager
from ..metadata import MediaMetadata, MediaType, Platform
from ..middlewares import Middleware
from ..util import FrozenDict

DEFAULT_INSTALOADER_KWARGS = FrozenDict(
    {
        "save_metadata": False,
        "download_video_thumbnails": False,
        "quiet": True,  # logs by default to stdout, so we don't want to do that
        "sleep": True,
        "filename_pattern": "{target}",
        "post_metadata_txt_pattern": "",  # Don't save
        "storyitem_metadata_txt_pattern": "",  # Don't save
    }
)
DEFAULT_INSTALOADER = Instaloader(**DEFAULT_INSTALOADER_KWARGS)
# All of these will be initialized concurrently, and we don't want them to clobber each other
DEFAULT_INSTALOADER_SETUP_LOCK = Lock()
DEFAULT_INSTALOADER_INITIALIZED = Event()


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
        use_default_instaloader: bool = True,
        # Username to watch
        username: str | None = None,
        userid: int | None = None,
        **config,
    ) -> None:
        super().__init__(name, preprocessors, **config)

        self._copy = copy
        self._backtrack = backtrack

        # build off of defaults
        self._iloader_kwargs: dict[str, Any] | None
        if instaloader_kwargs is not None:
            self._iloader_kwargs = dict(DEFAULT_INSTALOADER_KWARGS)
            self._iloader_kwargs.update(instaloader_kwargs)
        else:
            self._iloader_kwargs = None

        self._proxies = proxies

        self._use_default_iloader = use_default_instaloader
        self._iloader: Instaloader | None = None
        self._profile: Profile | None = None

        if username is None and userid is None:
            raise ValueError("Either username or userid must be specified!")

        self._username = username
        self._userid = userid

    def close(self) -> None:
        super().close()
        if self._iloader is not None and self._use_default_iloader:
            self._iloader.close()

    @property
    def _session(self) -> Session:
        assert self._iloader is not None, "InstaloaderWatcher not prepared!"
        return self._iloader.context._session  # noqa

    def prepare(
        self,
        shutdown_event: Event,
        callback: UploadCallback,
        pool: ConnectionPool,
        file_manager: FileManager,
        **kwargs,
    ) -> None:
        super().prepare(shutdown_event, callback, pool, file_manager, **kwargs)

        assert self._file_manager is not None, "File manager was not set!"

        # I don't like doing this, but performance and memory usage is important as well as not getting railed by
        # instagram's bot detection.
        if self._use_default_iloader:
            with DEFAULT_INSTALOADER_SETUP_LOCK:
                if self._iloader_kwargs is not None:
                    self.logger.warning(
                        "Ignoring instaloader_kwargs when using default instaloader! "
                        "Set use_default_instaloader to False to instantiate a custom instaloader."
                    )
                if self._proxies is not None:
                    self.logger.warning(
                        "Ignoring proxies when using default instaloader! "
                        "Set use_default_instaloader to False to instantiate a custom instaloader."
                    )

                self._iloader_kwargs = dict(DEFAULT_INSTALOADER_KWARGS)
                self._iloader = DEFAULT_INSTALOADER

                if not DEFAULT_INSTALOADER_INITIALIZED.is_set():
                    # We can't set this up at compile time, so we have to do it here.
                    # We are assured by the Event and the Lock that this can only possibly run once, and by the nature
                    # of the setup that things like the shutdown_event, upload callback, file manager, etc. will be the
                    # same for all instances of this class.
                    DEFAULT_INSTALOADER.dirname_pattern = str(
                        self._file_manager.directory
                    )

                    # Login behavior is different for the default instaloader, so we have to do this here.
                    username = environ.get("FREEBOOTER_INSTALOADER_USERNAME")
                    session_file = environ.get("FREEBOOTER_INSTALOADER_SESSION_FILE")
                    if username is not None:
                        session_filename = None
                        if session_file is not None:
                            session_file_path = Path(session_file)

                            if not session_file_path.is_absolute():
                                session_file_path = session_file_path.absolute()

                            if not session_file_path.is_file():
                                self.logger.warning("Session file does not exist!")

                            session_filename = str(session_file_path)

                        DEFAULT_INSTALOADER.load_session_from_file(
                            username, session_filename
                        )

                    # This is hacky as all shit! But, there is no other way to guarantee that the default instaloader
                    # will shut down properly. This is because the default instaloader is a singleton, and we can't
                    # have it be shut down by any of the individual instances of this class.
                    def safe_shutdown() -> None:
                        shutdown_event.wait()
                        DEFAULT_INSTALOADER.close()
                        return

                    default_instaloader_shutdown_thread = Thread(
                        target=safe_shutdown,
                        name="DefaultInstaloaderGracefulShutdownGuaranteer6000",  # humorous, no other reason
                    )
                    default_instaloader_shutdown_thread.start()

                    DEFAULT_INSTALOADER.__shutdown_thread = default_instaloader_shutdown_thread  # type: ignore  # idc, custom

                    DEFAULT_INSTALOADER_INITIALIZED.set()

                self._iloader_kwargs.setdefault(
                    "dirname_pattern", self._iloader.dirname_pattern
                )
        else:
            if self._iloader_kwargs is None:
                self._iloader_kwargs = {}

            self._iloader_kwargs.setdefault(
                "dirname_pattern", str(self._file_manager.directory)
            )
            self._iloader = Instaloader(**self._iloader_kwargs)

            if self._proxies is not None:
                self._session.proxies.update(self._proxies)
        if self._username is not None:
            try:
                self._profile = Profile.from_username(
                    self._iloader.context, self._username
                )
            except ProfileNotExistsException:
                if self._userid:
                    self.logger.warning(
                        f"Profile with username {self._username} does not exist, using userid instead."
                    )
                    self._profile = Profile.from_id(self._iloader.context, self._userid)
                else:
                    raise
        elif self._userid is not None:
            self._profile = Profile.from_id(self._iloader.context, self._userid)

        assert self._profile is not None, "A profile was not found!"

    def _check_for_uploads_generator(
        self,
    ) -> Generator[tuple[ScratchFile, MediaMetadata], None, None]:
        assert self._profile is not None, "A profile was not found!"
        assert self._iloader is not None, "Instaloader was not initialized!"
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

            self._iloader.download_post(post, file_ident)

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

            # Files from albums may noy show up so we need to check for them.
            # TODO: 12345677_1.jpg is the second image in an album, 12345677_2.jpg is the third, etc.
            # Only 12345677.jpg is the first image and is the only one that we handle.

            yield file, metadata

            self.mark_handled(post.shortcode)

        if self._copy:
            self._copy = False

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        return list(self._check_for_uploads_generator())


__all__ = ("InstaloaderWatcher",)
