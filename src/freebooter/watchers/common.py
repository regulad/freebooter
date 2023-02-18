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

from abc import ABCMeta
from concurrent.futures import Future
from logging import Logger
from logging import getLogger
from threading import Event
from threading import Thread
from typing import Callable
from typing import TYPE_CHECKING, TypeAlias

from mariadb import ConnectionPool, Connection, Cursor

from ..file_management import FileManager
from ..file_management import ScratchFile
from ..metadata import MediaMetadata
from ..middlewares import Middleware

if TYPE_CHECKING:
    UploadCallback: TypeAlias = Callable[
        [list[tuple[ScratchFile, MediaMetadata]]],
        Future[list[tuple[ScratchFile, MediaMetadata | None]]],
    ]
    # This is the type of the callback that is called when a watcher finds new media. You plug in the list of tuples
    # of the downloaded file and the metadata for the upload. You receive a future that will be set when the upload
    # is complete. This future contains the ScratchFile of the uploaded file and the MediaMetadata of the uploaded
    # file on the platform it was uploaded to.
else:
    # This is here to allow other modules to import this module during runtime when TYPE_CHECKING is False
    UploadCallback = object

logger: Logger = getLogger(__name__)


class Watcher(Thread, metaclass=ABCMeta):
    """
    This thread watches a channel on a streaming server for new videos and downloads them and then calls the return_call
    """

    MYSQL_TYPE: str | None = "VARCHAR(255)"
    SLEEP_TIME: float = 30.0

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        **config,
    ) -> None:
        super().__init__(
            name=f"{self.__class__.__name__}-{name.title().replace(' ', '-')}"
        )

        self._table_name = self.name
        self.preprocessors = preprocessors

        self._shutdown_event: Event | None = None
        self._callback: UploadCallback | None = None
        self._mariadb_pool: ConnectionPool | None = None
        self._file_manager: FileManager | None = None

    @property
    def logger(self) -> Logger:
        return getLogger(self.name)

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        """
        Checks for new uploads and downloads them.
        :return: A list of tuples of the downloaded file and the metadata for the upload
        """
        raise NotImplementedError

    @property
    def ready(self) -> bool:
        return (
            self._shutdown_event is not None
            and self._callback is not None
            and self._mariadb_pool is not None
            and self._file_manager is not None
            and all(middleware.ready for middleware in self.preprocessors)
        )

    def prepare(
        self,
        shutdown_event: Event,
        callback: UploadCallback,
        pool: ConnectionPool,
        file_manager: FileManager,
    ) -> None:
        assert not self.ready, "Watcher is already ready!"

        for middleware in self.preprocessors:
            middleware.prepare(shutdown_event, file_manager)

        self._shutdown_event = shutdown_event
        self._callback = callback
        self._mariadb_pool = pool
        self._file_manager = file_manager

        assert self.ready, "An error occurred while readying uploader!"

    def close(self) -> None:
        assert self.ready, "Watcher is not ready!"

    def start(self) -> None:
        assert self.ready, "Watcher is not ready!"
        if self.MYSQL_TYPE is not None:
            self.make_tables()
        super().start()

    def mark_handled(self, id_: str, is_handled: bool = True) -> None:
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

    def is_handled(self, id_: str) -> bool:
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
        assert self.ready, "Watcher is not ready!"
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

    def run(self) -> None:
        assert self.ready, "Watcher is not ready, cannot run thread!"
        assert (
            self._shutdown_event is not None
        ), "Watcher is not ready, cannot run thread!"
        assert self._callback is not None, "Watcher is not ready, cannot run thread!"

        while not self._shutdown_event.is_set():
            self.logger.debug(
                f"{self.name}, a {self.__class__.__name__}, is running a check cycle..."
            )

            try:
                downloaded = self.check_for_uploads()
            except Exception as e:
                self.logger.exception(f"Error checking for new uploads: {e}")
                downloaded = []

            for preprocessor in self.preprocessors:
                downloaded = preprocessor.process_many(downloaded)

            # The following is a bit dirty, but it is very difficult to close out the files since the rest of the
            # code is concurrent
            def cleanup(
                done_future: Future[list[tuple[ScratchFile, MediaMetadata | None]]]
            ) -> None:
                try:
                    result = done_future.result(timeout=0)
                except TimeoutError:
                    result = None

                if result is None:
                    self.logger.error(
                        "Upload callback timed out, closing files and exiting"
                    )
                    if downloaded is not None:
                        for scratch_file, _ in downloaded:
                            if not scratch_file.closed:
                                scratch_file.close()
                else:
                    self.logger.debug("Upload callback finished, closing files")
                    for scratch_file, _ in result:
                        if not scratch_file.closed:
                            scratch_file.close()

            uploaded_future = self._callback(downloaded)
            uploaded_future.add_done_callback(cleanup)

            self.logger.info(
                f"{self.name} completed a check cycle with {len(downloaded)} output(s), sleeping.."
            )
            self._shutdown_event.wait(self.SLEEP_TIME)


__all__ = ("Watcher", "UploadCallback")
