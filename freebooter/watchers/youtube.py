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
from logging import getLogger
from pathlib import Path
from traceback import format_exc
from typing import TYPE_CHECKING

from .common import *  # for RETURN_TYPE during type checking
from ..metadata import MediaMetadata

if TYPE_CHECKING:
    from threading import Event
    from logging import Logger
    from typing import Literal

    from mariadb import ConnectionPool

    from ..file_management import FileManager

logger: "Logger" = getLogger(__name__)

CHANNEL_URL_BASENAMES: set[str] = {"videos", "playlists"}


# These are playlists that are on a channel, like videos or playlists
# I like to think of these as "root playlists" as part of the channel
# todo: figure out how shorts work on ytdl (i don't think they do)


class YouTubeChannelWatcher(YTDLWatcher):
    """
    This class runs a thread that pulls YouTube vidoes
    """

    ID_SQL_TYPE: str = "CHAR(11)"  # YouTube IDs are 11 characters long

    def __init__(
            self,
            shutdown_event: "Event",
            return_call: "RETURN_TYPE",
            pool: "ConnectionPool",
            file_manager: "FileManager",
            copy: bool,
            # YouTube specific
            channel_id: str,
            root_playlist: "Literal[CHANNEL_URL_BASENAMES]" = "videos",  # todo: have this as an argument
            **ytdl_params,
    ) -> None:
        """
        :param channel_id: The YouTube channel ID to watch. This is the channel ID, not the username. Example: 'UC7Jwj9fkrf1adN4fMmTkpug'
        :param ytdl_params: Parameters to pass to youtube-dl
        """

        assert root_playlist in CHANNEL_URL_BASENAMES, f"root_playlist must be one of {CHANNEL_URL_BASENAMES}"

        assert channel_id.startswith("UC"), "Channel ID must start with UC"
        assert len(channel_id) == 24, "Channel ID must be 24 characters long"

        name: str = f"yt-{channel_id}"

        super().__init__(name=name, shutdown_event=shutdown_event, return_call=return_call,
                         table_name=name, pool=pool, file_manager=file_manager, copy=copy, **ytdl_params)

        self._channel_id: str = channel_id
        self._root_playlist: str = root_playlist
        self._channel_url: str = f"https://www.youtube.com/channel/{channel_id}"

    def _handle_video(self, video_id: str, handle_if_already_handled: bool = False) -> bool:
        """
        :param video_id: The ID of the video to download
        :param handle_if_already_handled: If True, the video will be downloaded even if it is already in the database
        :return: True if the video was handled (now or previously), False if it was skipped or if an error occurred
        """

        assert self._connection is not None, "Connection is None, this method should only be called in the run"

        logger.info(f"Handling video {video_id}...")

        if not handle_if_already_handled and self.is_handled(video_id):
            logger.info(f"Video {video_id} is already handled, skipping...")
            return True  # already handled
        else:
            handled: bool = False
            try:
                logger.info(f"Downloading video {video_id}...")
                info: dict = self._downloader.extract_info(video_id, download=True)

                filename: str = self._downloader.prepare_filename(info)

                filepath: "Path" = Path(filename)

                if not filepath.exists():
                    # ok, so the file doesn't exist.
                    # Sometimes, if ffmpeg is installed, youtube-dl will use it to merge the files into an mkv.
                    # let's try that.
                    mkv_filepath = filepath.with_suffix(".mkv")
                    if not mkv_filepath.exists():
                        raise FileNotFoundError(f"File {filepath} does not exist! cannot continue")
                    else:
                        filepath = mkv_filepath  # good enough, we can continue with this mkv.

                with self._file_manager.get_file(file_name=filepath) as scratch_file:
                    metadata: "MediaMetadata" = MediaMetadata.from_ytdl_info(info)

                    try:
                        uploaded_videos: list[MediaMetadata] = self._return_call(scratch_file, metadata)
                        handled = True  # maybe len(uploaded_videos) > 0 but nah
                    except Exception as e:
                        logger.error(f"Miscellaneous exception running callback video {video_id}: {e}")
                        logger.debug(format_exc())
            except Exception as e:
                logger.exception(f"Error downloading video {video_id}: {e}")
                logger.exception(format_exc())
                return False
            else:
                self.mark_handled(video_id, True)
                return handled

    def check_for_uploads(self) -> bool:
        """
        Checks for new uploads on the channel
        :return: True if any videos were handled, False otherwise
        """

        assert self._connection is not None, "Connection is None, this method should only be called in the run"

        logger.info(f"Checking for uploads on YouTube channel {self._channel_id}..")

        handled: bool = False

        try:
            info: dict = self._downloader.extract_info(self._channel_url, download=False)
            # returns playlist style info

            playlists: list[dict] = info["entries"]

            playlist: dict | None = next(
                (
                    playlist for playlist in playlists if playlist.get("webpage_url_basename")
                                                          == self._root_playlist
                ),
                None
            )

            assert playlist is not None, \
                f"Could not find playlist of which had a webpage with a url with a path of {self._root_playlist} " \
                f"on channel {self._channel_id}"

            videos: list[dict] = playlist["entries"]

            if not self._copy and len(videos) > 1:  # i.e. we are not copying, just uploading the latest video
                videos = videos[:1]  # only get the latest video

            for video in videos:
                if self._handle_video(video["id"]):
                    handled = True
        except Exception as e:
            logger.exception(f"Error checking for uploads: {e}")
            logger.exception(format_exc())
            return False
        else:
            return handled


__all__: tuple[str] = (
    "YouTubeChannelWatcher",
)
