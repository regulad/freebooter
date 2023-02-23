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

from logging import Logger
from logging import getLogger
from traceback import format_exc
from typing import Generator

from .common import YTDLThreadWatcher
from ..file_management import ScratchFile
from ..metadata import MediaMetadata
from ..middlewares import Middleware

logger: Logger = getLogger(__name__)


class YTDLYouTubeChannelWatcher(YTDLThreadWatcher):
    """
    This class runs a thread that pulls YouTube vidoes
    """

    MYSQL_TYPE = "CHAR(24)"
    SLEEP_TIME = 60 * 60 * 1  # one hour

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        channel_id: str,
        playlist: str | None = None,
        shorts: bool = False,
        backtrack: bool = False,
        copy: bool = False,
        **config,
    ) -> None:
        """
        :param channel_id: The YouTube channel ID to watch. This is the channel ID, not the username. Example: 'UC7Jwj9fkrf1adN4fMmTkpug'
        :param ytdl_params: Parameters to pass to youtube-dl
        """

        if not (channel_id.startswith("UC") and len(channel_id) == 24):
            raise ValueError(
                "Invalid channel ID. Channel ID must start with UC and be 24 characters long"
            )

        super().__init__(
            name,
            preprocessors,
            **config,
        )

        self._channel_id = channel_id
        self._playlist = playlist
        self._shorts = shorts
        self._copy = copy
        self._backtrack = backtrack

    @property
    def _channel_url(self) -> str:
        return f"https://www.youtube.com/channel/{self._channel_id}"

    def _prepare_video(
        self, video_id: str, handle_if_already_handled: bool = False
    ) -> tuple[ScratchFile, MediaMetadata] | None:
        """
        :param video_id: The ID of the video to download
        :param handle_if_already_handled: If True, the video will be downloaded even if it is already in the database
        :return: True if the video was handled (now or previously), False if it was skipped or if an error occurred
        """
        assert self._file_manager is not None, "File manager is not set!"
        assert self._downloader is not None, "Downloader is not set!"

        self.logger.debug(f"Handling video {video_id}...")

        if not handle_if_already_handled and self.is_handled(video_id):
            self.logger.debug(f"Video {video_id} is already handled, skipping...")
            return None
        else:
            try:
                scratch_file, metadata = self._download(video_id)
                self.mark_handled(video_id, True)
                return scratch_file, metadata
            except Exception as e:
                self.logger.exception(f"Error downloading video {video_id}: {e}")
                self.logger.exception(format_exc())
                return None

    def check_for_uploads(self) -> list[tuple[ScratchFile, MediaMetadata]]:
        assert self.ready, "Watcher is not ready!"
        assert self._downloader is not None, "Downloader is not set!"

        self.logger.info(
            f"Checking for uploads on YouTube channel {self._channel_id}.."
        )

        try:
            # First, we need to get the list of playlists from the channels.
            info: dict = self._downloader.extract_info(
                self._channel_url, download=False, process=False
            )

            playlists: list[dict] = info["entries"]

            # Now, we need to select the desired playlist.
            chosen_playlist: dict | None = None
            if self._shorts and self._playlist is None:
                for playlist in playlists:
                    playlist_title = playlist.get("title")
                    if playlist_title is not None and "- Shorts" in playlist_title:
                        chosen_playlist = playlist
                        break
            elif not self._shorts and self._playlist is None:
                for playlist in playlists:
                    playlist_title = playlist.get("title")
                    if playlist_title is not None and "- Videos" in playlist_title:
                        chosen_playlist = playlist
                        break
            else:
                for playlist in playlists:
                    playlist_title = playlist.get("title")
                    if playlist_title is not None and self._playlist == playlist_title:
                        chosen_playlist = playlist
                        break

            if chosen_playlist is None:
                self.logger.error(
                    f"Could not find playlist {self._playlist} on channel {self._channel_id}!"
                )
                return []

            videos: Generator[dict, None, None] = chosen_playlist["entries"]

            # Now, let's download the videos
            ready_prepared: list[tuple[ScratchFile, MediaMetadata]] = []

            if self._backtrack:
                video_list: list[dict] = list(videos)
                video_list.reverse()  # get the oldest videos first
                for video in video_list:
                    prepared = self._prepare_video(video["id"], self._copy)
                    if prepared is not None:
                        ready_prepared.append(prepared)
            else:
                video = videos.__next__()
                prepared = self._prepare_video(video["id"], self._copy)
                if prepared is not None:
                    ready_prepared.append(prepared)

            if self._copy:
                self._copy = False

            return ready_prepared
        except Exception as e:
            logger.exception(f"Error checking for uploads: {e}")
            logger.exception(format_exc())
            return []


__all__ = ("YTDLYouTubeChannelWatcher",)
