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

import asyncio
import time
from abc import ABCMeta
from asyncio import AbstractEventLoop, Task
from concurrent.futures import Future
from logging import Logger
from logging import getLogger
from os import sep
from pathlib import Path
from threading import Event, Lock
from threading import Thread
from typing import Any, cast, ClassVar

from mariadb import ConnectionPool, Connection, Cursor

from ..file_management import FileManager
from ..file_management import ScratchFile
from ..metadata import MediaMetadata
from ..middlewares import Middleware
from ..types import UploadCallback

logger = getLogger(__name__)

# I don't trust yt-dlp to be backwards compatible with youtube_dl *perfectly*, so I'm going to try to import yt-dlp
# first, and for any errors, I'll fall back to youtube_dl.
try:
    from yt_dlp import YoutubeDL  # type: ignore
except ImportError:
    logger.warning("yt-dlp failed to compile or not found, falling back to youtube_dl")
    from youtube_dl import YoutubeDL  # type: ignore


class Watcher(metaclass=ABCMeta):
    """
    This class is the base class for all watchers. It contains some common functionality that all watchers need.
    """

    MYSQL_TYPE: ClassVar[str | None] = "VARCHAR(255)"

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        copy: bool = False,
        backtrack: int | None = 0,
        process_if_empty: bool = False,
        **config,
    ) -> None:
        if not hasattr(self, "name"):  # for subclasses that inherit from thread
            self.name = f"{self.__class__.__name__}-{name.title().replace(' ', '-')}"

        self._table_name = self.name
        self.preprocessors = preprocessors

        self._shutdown_event: Event | None = None
        self._callback: UploadCallback | None = None
        self._mariadb_pool: ConnectionPool | None = None
        self._file_manager: FileManager | None = None
        self._loop: AbstractEventLoop | None = None

        self._backtrack = backtrack
        self._copy = copy
        self._process_if_empty = process_if_empty

        self._extra_kwargs: dict[str, Any] = config.copy()
        self._extra_prep_kwargs: dict[str, Any] = {}

    def close(self) -> None:
        """
        Closes the watcher. This may be a coroutine, but doesn't have to be.
        """
        assert self.ready, "Watcher is not ready!"

        self.logger.debug(f"Closing watcher {self.name}...")
        for middleware in self.preprocessors:
            middleware.close()

    @property
    def logger(self) -> Logger:
        return getLogger(self.name)

    def prepare(
        self,
        **kwargs,
    ) -> None:
        if self.ready:
            self.logger.warning(f"{self.name} is already ready! Prepare may have unintended consequences.")

        self.logger.debug(f"Preparing {self.name}...")

        for middleware in self.preprocessors:
            middleware.prepare(**kwargs)

        self._shutdown_event = kwargs["shutdown_event"]
        self._callback = kwargs["callback"]
        self._mariadb_pool = kwargs["pool"]
        self._file_manager = kwargs["file_manager"]
        self._loop = kwargs["event_loop"]

        self._extra_prep_kwargs |= kwargs

        if self.MYSQL_TYPE is not None:
            self.make_tables()

    @property
    def ready(self) -> bool:
        return (
            self._shutdown_event is not None
            and self._callback is not None
            and self._mariadb_pool is not None
            and self._file_manager is not None
            and all(middleware.ready for middleware in self.preprocessors)
        )

    def mark_handled(self, id_: Any, is_handled: bool = True) -> None:
        """
        Marks the given ID as handled in the database
        :param id_: The ID to mark as handled
        :param is_handled: Whether the ID is handled
        :return:
        """
        assert self.ready, "Watcher is not ready!"
        assert self._mariadb_pool is not None, "Watcher is not ready!"
        with self._mariadb_pool.get_connection() as connection, connection.cursor() as cursor:  # type: Connection, Cursor
            cursor.execute(
                f"""
                INSERT INTO `{self._table_name}` (id, handled) VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE handled = %s;
                """,
                (id_, is_handled, is_handled),
            )
            connection.commit()
            self.logger.debug(f"Marked {id_} as handled: {is_handled}")

    def is_handled(self, id_: Any) -> bool:
        """
        Checks if the given ID is handled
        :param id_: The ID to check
        :return: Whether the ID is handled
        """
        assert self.ready, "Watcher is not ready!"
        assert self._mariadb_pool is not None, "Watcher is not ready!"
        with self._mariadb_pool.get_connection() as connection, connection.cursor() as cursor:  # type: Connection, Cursor
            cursor.execute(
                f"""
                SELECT handled FROM `{self._table_name}` WHERE id = %s;
                """,
                (id_,),
            )
            result: tuple[bool] | None = cursor.fetchone()
            self.logger.debug(f"Result of is_handled: {result}")
            return result is not None and result[0]

    def make_tables(self) -> None:
        """
        Initializes the tables for the watcher.
        A subclass may override this to make more tables or tables with a different schema.
        :return:
        """
        assert self._mariadb_pool is not None, "Watcher is not ready!"
        with self._mariadb_pool.get_connection() as connection, connection.cursor() as cursor:  # type: Connection, Cursor
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{self._table_name}` (
                    id {self.MYSQL_TYPE} NOT NULL,
                    handled BOOLEAN NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (id)
                );
                """
            )
            connection.commit()
            self.logger.debug(f"Created table {self._table_name}")

    def _preprocess_and_execute(
        self, downloaded: list[tuple[ScratchFile, MediaMetadata]]
    ) -> Future[list[tuple[ScratchFile, MediaMetadata | None]]]:
        assert self._callback, "No callback set!"

        self.logger.info(f"{self.name} found {len(downloaded)} new uploads, processing...")

        preprocessed: list[tuple[ScratchFile, MediaMetadata | None]] = cast(
            "list[tuple[ScratchFile, MediaMetadata | None]]",
            # mypy doesn't get the hint of casting a non-optional to an optional, so we have to do this.
            downloaded.copy(),
        )
        for preprocessor in self.preprocessors:
            preprocessed = preprocessor.process_many(preprocessed)

        def _affirm_result(done_future: Future[list[tuple[ScratchFile, MediaMetadata | None]]]) -> None:
            try:
                result = done_future.result(timeout=0)
            except TimeoutError:
                result = None

            for _, metadata in downloaded:
                self.mark_handled(metadata.id)

            if result is None:
                self.logger.error(f"{self.name} upload callback failed!")
            else:
                self.logger.debug(f"{self.name} upload callback finished.")

        self.logger.debug(f"Calling back with {len(preprocessed)} medias... ")

        fut = self._callback(preprocessed)

        fut.add_done_callback(_affirm_result)

        return fut


class AsyncioWatcher(Watcher):
    """
    A watcher that runs on the asyncio event loop.
    """

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        **config,
    ) -> None:
        super().__init__(name, preprocessors, **config)
        self._prepare_task: Task | None = None
        self._closing_task: Task | None = None

        self._process_lock = asyncio.Lock()

    async def aprocess(self, medias: list[tuple[ScratchFile, MediaMetadata]]) -> list[MediaMetadata]:
        """
        A coroutine that preprocesses and executes the given medias.
        :param medias: The medias to preprocess and execute
        :return: A future that resolves to the processed medias
        """
        async with self._process_lock:
            assert self._loop is not None, "No event loop set!"

            asyncio_future_concurrent_future = self._loop.run_in_executor(None, self._preprocess_and_execute, medias)
            concurrent_future = await asyncio_future_concurrent_future
            asyncio_future = asyncio.wrap_future(concurrent_future, loop=self._loop)

            list_of_medias = await asyncio_future

            return [metadata for _, metadata in list_of_medias if metadata is not None]

    async def async_prepare(self) -> None:
        """
        An async method that is called when the watcher is prepared.
        This will be called when the entire program is ready to go and the event loop is running.
        """
        self.logger.debug(f"Preparing watcher {self.name} asynchronously...")

    async def aclose(self) -> None:
        """
        Closes the watcher asynchronously.
        """
        self.logger.debug(f"Closing watcher {self.name} asynchronously...")

    def close(self) -> None:
        """
        Closes the watcher.
        """
        super().close()
        if self._loop is not None:
            if self._loop.is_running():
                if asyncio.get_event_loop() is not self._loop:
                    # We are on a different thread, so we need to schedule the close
                    self._loop.call_soon_threadsafe(self._loop.create_task, self.aclose())
                else:
                    # We are on the same thread, so we can just schedule the close
                    self._closing_task = self._loop.create_task(self.aclose())
            else:
                self._loop.run_until_complete(self.aclose())

    @property
    def ready(self) -> bool:
        return super().ready and self._prepare_task is not None and self._prepare_task.done()

    def prepare(self, **kwargs) -> None:
        super().prepare(**kwargs)

        assert self._loop is not None, "No event loop set!"

        self._prepare_task = self._loop.create_task(self.async_prepare())


class ThreadWatcher(Thread, Watcher, metaclass=ABCMeta):  # type: ignore  # I know thread clobbers the name
    """
    This thread watches a channel on a streaming server for new videos and downloads them and then calls the return_call
    """

    # Instance variable for special handling of the sleep_time
    sleep_time: float = 60.0

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        **config,
    ) -> None:
        self._name = f"{self.__class__.__name__}-{name.title().replace(' ', '-')}"

        Thread.__init__(self, name=self._name)
        Watcher.__init__(self, self.name, preprocessors, **config)

        self._process_lock = Lock()

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        """
        Checks for new uploads and downloads them.
        :return: A list of tuples of the downloaded file and the metadata for the upload
        """
        raise NotImplementedError

    def close(self) -> None:
        super().close()

        if self._shutdown_event is not None and self._shutdown_event.is_set():
            self.join()  # just wait for it to spin down

    def process(self, medias: list[tuple[ScratchFile, MediaMetadata]]) -> list[MediaMetadata]:
        with self._process_lock:
            fut = self._preprocess_and_execute(medias)
            return [metadata for _, metadata in fut.result() if metadata is not None]

    def run(self) -> None:
        assert self.ready, "Watcher is not ready, cannot run thread!"
        assert self._shutdown_event is not None, "Watcher is not ready, cannot run thread!"
        assert self._callback is not None, "Watcher is not ready, cannot run thread!"

        while not self._shutdown_event.is_set():
            self.logger.debug(f"{self.name}, a {self.__class__.__name__}, is running a check cycle...")

            try:
                downloaded = self.check_for_uploads()
            except Exception as e:
                self.logger.exception(f"Error checking for new uploads: {e}")
                downloaded = []
            else:
                if self._copy:
                    self._copy = False
                if self._backtrack:
                    self._backtrack = False

            if downloaded:
                start = time.perf_counter()
                self.process(downloaded)
                elapsed = time.perf_counter() - start
            else:
                elapsed = 0.0

            self._shutdown_event.wait(max(self.sleep_time - elapsed, 0.0))


class YTDLThreadWatcher(ThreadWatcher, metaclass=ABCMeta):
    """
    This watcher uses youtube-dl to download videos from a channel.
    """

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        ytdl_params: dict | None = None,
        **config,
    ) -> None:
        """
        :param ytdl_params: Parameters to pass to the youtube-dl downloader constructor (see youtube_dl.YoutubeDL)
        """
        if ytdl_params is None:
            ytdl_params = {}

        assert ytdl_params is not None, "ytdl_params must not be None"  # for mypy

        super().__init__(name=name, preprocessors=preprocessors, **config)

        self._ytdl_params: dict = ytdl_params

        self._ytdl_params.setdefault("logger", self.logger)

        self._downloader: YoutubeDL | None = None

    def _download(self, query: str) -> tuple[ScratchFile, MediaMetadata]:
        assert self._downloader is not None, "Downloader not initialized"
        assert self._file_manager is not None, "File manager not initialized"

        self.logger.debug(f'Downloading video with query "{query}"...')

        info: dict = self._downloader.extract_info(query, download=True)

        filename: str = self._downloader.prepare_filename(info)

        filepath = Path(filename)

        scratch_file = self._file_manager.get_file(file_name=filepath)

        metadata = MediaMetadata.from_ytdl_info(info)

        return scratch_file, metadata

    def close(self) -> None:
        super().close()
        del self._downloader  # ytdl does some closing but not openly
        self._downloader = None

    def prepare(self, **kwargs) -> None:
        super().prepare(**kwargs)

        assert self._downloader is None, "Downloader already initialized"
        assert self._file_manager is not None, "File manager not initialized"

        self._ytdl_params.setdefault("outtmpl", f"{self._file_manager.directory}{sep}%(id)s.%(ext)s")

        self._downloader = YoutubeDL(self._ytdl_params)


__all__ = (
    "Watcher",
    "AsyncioWatcher",
    "ThreadWatcher",
    "YTDLThreadWatcher",
)
