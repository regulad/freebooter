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
from abc import ABCMeta
from logging import getLogger
from os import sep
from threading import Thread
from time import sleep
from typing import TYPE_CHECKING, Type

from youtube_dl import YoutubeDL, DEFAULT_OUTTMPL

from ..file_management import ScratchFile
from ..metadata import MediaMetadata

if TYPE_CHECKING:
    from logging import Logger
    from typing import Callable
    from mariadb import ConnectionPool, Connection, Cursor
    from threading import Event
    from ..file_management import FileManager

    RETURN_TYPE: Type = Callable[[ScratchFile, MediaMetadata], list[MediaMetadata]]

logger: "Logger" = getLogger(__name__)


class Watcher(Thread, metaclass=ABCMeta):
    """
    This thread watches a channel on a streaming server for new videos and downloads them and then calls the return_call
    """

    ID_SQL_TYPE: str = "VARCHAR(255)"  # Don't SQL inject yourself, dumbass.

    def __init__(
            self,
            name: str,
            shutdown_event: "Event",
            return_call: "RETURN_TYPE",
            table_name: str,
            pool: "ConnectionPool",
            file_manager: "FileManager",
            copy: bool
    ) -> None:
        super().__init__(name=f"Thread-{name.title().replace(' ', '-')}")
        self._shutdown_event = shutdown_event
        self._return_call: "RETURN_TYPE" = return_call
        self._table_name: str = table_name
        self._pool: "ConnectionPool" = pool
        self._file_manager: "FileManager" = file_manager
        self._copy: bool = copy
        self._connection: "Connection | None" = None

    def check_for_uploads(self) -> bool:
        """
        Checks for new uploads and downloads them then calls the return path if they are new
        :return: True if there was a change, False otherwise
        """
        assert self._connection is not None, "Connection is None, this should never happen"
        raise NotImplementedError

    def start(self) -> None:
        with self._pool.get_connection() as connection:
            connection: "Connection"
            self._connection = connection
            try:
                self.make_tables()
            finally:
                self._connection = None
        super().start()

    def mark_handled(self, id_: str, is_handled: bool = True) -> None:
        """
        Marks the given ID as handled in the database
        :param id_: The ID to mark as handled
        :param is_handled: Whether the ID is handled
        :return:
        """
        assert self._connection is not None, "Connection is None, this should never happen"
        connection: "Connection" = self._connection
        with connection.cursor() as cursor:
            cursor: "Cursor"
            cursor.execute(
                f"""
                INSERT INTO `{self._table_name}` (id, handled) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE handled = %s;
                """,
                (id_, is_handled, is_handled)
            )
            connection.commit()

    def is_handled(self, id_: str) -> bool:
        """
        Checks if the given ID is handled
        :param id_: The ID to check
        :return: Whether the ID is handled
        """
        assert self._connection is not None, "Connection is None, this should never happen"
        connection: "Connection" = self._connection
        with connection.cursor() as cursor:
            cursor: "Cursor"
            cursor.execute(
                f"""
                SELECT handled FROM `{self._table_name}` WHERE id = %s;
                """,
                (id_,)
            )
            result: list[tuple[bool]] = cursor.fetchall()
            if len(result) == 0:
                return False
            return result[0][0]

    def make_tables(self) -> None:
        """
        Initalizes the tables for the watcher.
        A subclass may override this to make more tables or tables with a different schema.
        :return:
        """
        assert self._connection is not None, "Connection is None, this should never happen"
        connection: "Connection" = self._connection
        with connection.cursor() as cursor:
            cursor: "Cursor"
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{self._table_name}` (
                    id {self.__class__.ID_SQL_TYPE} NOT NULL,
                    handled BOOL NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (id)
                )
                """
            )
            connection.commit()
            logger.debug(f"Created table {self._table_name}")

    def run(self) -> None:
        while True:
            uploaded: bool = False

            if self._shutdown_event.is_set():
                # it would be good to check this during the sleep but i'm not sure how
                break  # shutdown peacefully
            with self._pool.get_connection() as connection:
                connection: "Connection"

                self._connection = connection

                try:
                    uploaded: bool = self.check_for_uploads()
                finally:
                    # we shouldn't need to do this, but having the connection on the watcher is good for utility
                    # an alternative is making the watcher or another class a Context Manager but this is fine
                    self._connection = None  # release

            sleep_seconds: float = 60.0 if uploaded else 300.0

            logger.info(f"{self.name} check cycle complete, sleeping for {sleep_seconds}...")
            sleep(sleep_seconds)


class YTDLWatcher(Watcher, metaclass=ABCMeta):
    """
    This watcher uses youtube-dl to download videos from a channel.
    """

    def __init__(
            self,
            name: str,
            shutdown_event: "Event",
            return_call: "RETURN_TYPE",
            table_name: str,
            pool: "ConnectionPool",
            file_manager: "FileManager",
            copy: bool,
            **ytdl_params,  # all other kwargs
    ) -> None:
        """
        :param ytdl_params: Parameters to pass to the youtube-dl downloader constructor (see youtube_dl.YoutubeDL)
        """
        super().__init__(name=name, shutdown_event=shutdown_event, return_call=return_call, table_name=table_name,
                         pool=pool, file_manager=file_manager, copy=copy)

        self._ytdl_params: dict = ytdl_params

        self._ytdl_params["outtmpl"] = str(self._file_manager.directory) + sep + DEFAULT_OUTTMPL

        self._ytdl_params["logger"] = logger

        self._downloader: "YoutubeDL" = YoutubeDL(params=self._ytdl_params)


__all__: tuple[str] = (
    "Watcher",
    "YTDLWatcher",
)

if TYPE_CHECKING:
    # this is really hacky but it simplifies the code a lot
    __all__ += (
        "RETURN_TYPE",
    )
