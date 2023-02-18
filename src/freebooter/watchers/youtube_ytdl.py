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

from .ytdl_common import YTDLWatcher
from ..file_management import ScratchFile
from ..metadata import MediaMetadata
from ..middlewares import Middleware

logger: Logger = getLogger(__name__)


class YTDLYouTubeChannelWatcher(YTDLWatcher):
    """
    This class runs a thread that pulls YouTube vidoes
    """

    MYSQL_TYPE = "CHAR(24)"

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        channel_id: str,
        playlist: str | None = None,
        copy: bool = False,
        **config,
    ) -> None:
        """
        :param channel_id: The YouTube channel ID to watch. This is the channel ID, not the username. Example: 'UC7Jwj9fkrf1adN4fMmTkpug'
        :param ytdl_params: Parameters to pass to youtube-dl
        """

        assert channel_id.startswith("UC"), "Channel ID must start with UC"
        assert len(channel_id) == 24, "Channel ID must be 24 characters long"

        name = f"yt-ytdl-{channel_id}" or name  # will never be used

        super().__init__(
            name,
            preprocessors,
            **config,
        )

        self._channel_id = channel_id
        self._playlist = playlist
        self._copy = copy

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
            if self._playlist is None:
                for playlist in playlists:
                    if (
                        playlist_title := playlist.get("title")
                    ) is not None and "Videos" in playlist_title:
                        chosen_playlist = playlist
                        break
            else:
                for playlist in playlists:
                    if (
                        playlist_title := playlist.get("title")
                    ) is not None and self._playlist == playlist_title:
                        chosen_playlist = playlist
                        break

            assert chosen_playlist is not None, (
                f"Could not find the playlist {self._playlist} "
                f"on channel {self._channel_id}"
            )

            videos: list[dict] = chosen_playlist["entries"]

            # Now, let's download the videos
            ready_prepared: list[tuple[ScratchFile, MediaMetadata]] = []
            for video in videos:
                prepared = self._prepare_video(video["id"], self._copy)
                if prepared is not None:
                    ready_prepared.append(prepared)
            return ready_prepared
        except Exception as e:
            logger.exception(f"Error checking for uploads: {e}")
            logger.exception(format_exc())
            return []


__all__ = ("YTDLYouTubeChannelWatcher",)
