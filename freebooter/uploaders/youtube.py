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
import json
from difflib import get_close_matches
from logging import getLogger
from traceback import format_exc
from typing import TYPE_CHECKING, cast

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from httplib2 import Http

from .common import Uploader
from ..metadata import Platform, MediaMetadata

if TYPE_CHECKING:
    from logging import Logger
    from io import IOBase
    from typing import Any
    from pathlib import Path

    from ..file_management import ScratchFile
    from .._schema_types import DesktopAppClientSecrets, OAuth2Token

    from googleapiclient._apis.youtube.v3.resources import (
        YouTubeResource,
        VideoHttpRequest,
        VideoCategoryListResponseHttpRequest,
        VideoCategoryListResponse,
        VideoCategory
    )
    from googleapiclient._apis.youtube.v3.schemas import Video
    from googleapiclient.discovery import Resource

logger: "Logger" = getLogger(__name__)

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


class YouTubeUploader(Uploader):
    def __init__(self, client_secret_data: "DesktopAppClientSecrets", oauth2_token_data: "OAuth2Token",
                 youtube_api_key: str) -> None:
        super().__init__()

        self._http_handler = Http()

        self._credentials: "Credentials" = Credentials(
            token=oauth2_token_data["access_token"],
            refresh_token=oauth2_token_data["refresh_token"],
            token_uri=client_secret_data["installed"]["token_uri"],
            client_id=client_secret_data["installed"]["client_id"],
            client_secret=client_secret_data["installed"]["client_secret"],
            scopes=oauth2_token_data["scope"],
            # off by default for some reason
            enable_reauth_refresh=True,
        )

        uncast_oauth_resource: "Resource" = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                                                  credentials=self._credentials)

        uncast_dev_key_resource: "Resource" = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                                                    developerKey=youtube_api_key, http=self._http_handler)

        self._youtube_oauth_resource: "YouTubeResource" = cast("YouTubeResource", uncast_oauth_resource)
        self._youtube_dev_key_resource: "YouTubeResource" = cast("YouTubeResource", uncast_dev_key_resource)

    @classmethod
    def create_from_config_files(cls, config_folder: "Path", channel_name: str,
                                 youtube_api_key: str) -> "YouTubeUploader":
        client_secret_path: "Path" = config_folder / (channel_name + ".json")
        oauth2_token_path: "Path" = config_folder / (channel_name + "-oauth2.json")

        with client_secret_path.open("r") as client_secret_file, oauth2_token_path.open("r") as oauth2_token_file:
            client_secret_data: "DesktopAppClientSecrets" = json.load(client_secret_file)
            oauth2_token_data: "OAuth2Token" = json.load(oauth2_token_file)

        return cls(client_secret_data, oauth2_token_data, youtube_api_key)

    def close(self) -> None:
        with self._lock:
            self._http_handler.close()
            del self._credentials  # does not close?

    def _get_category_id(self, category_name: str) -> int:
        """
        Returns the closest matching category ID for the given category name.
        :param category_name: The name of the category to get the ID for.
        :return: Category ID, or 22 (People & Blogs) if no match is found.
        """
        video_categories_resource: "YouTubeResource.VideoCategoriesResource" = \
            self._youtube_dev_key_resource.videoCategories()
        video_categories_http_request: "VideoCategoryListResponseHttpRequest" = \
            video_categories_resource.list(regionCode="US", part="snippet")
        video_category_list_response: "VideoCategoryListResponse" = \
            video_categories_http_request.execute(num_retries=MAX_RETRIES)
        category_list: "list[VideoCategory]" = video_category_list_response["items"]  # type: ignore

        safe_categories: "dict[str, int]" = {}

        for category in category_list:
            if category["snippet"]["assignable"]:
                category_id: int = int(category["id"])
                category_title: str = category["snippet"]["title"]

                safe_categories[category_title] = category_id
            else:
                continue  # we can't assign it so we might as well skip it

        close_matches: "list[int]" = [
            safe_categories[str(match)] for match in get_close_matches(category_name, safe_categories.keys())
        ]

        if len(close_matches) == 0:
            return 22  # we tried
        else:
            return close_matches[0]

    def _get_category_name(self, category_id: int) -> str:
        video_categories_resource: "YouTubeResource.VideoCategoriesResource" = \
            self._youtube_dev_key_resource.videoCategories()
        video_categories_http_request: "VideoCategoryListResponseHttpRequest" = \
            video_categories_resource.list(regionCode="US", part="snippet")
        video_category_list_response: "VideoCategoryListResponse" = \
            video_categories_http_request.execute(num_retries=MAX_RETRIES)
        category_list: "list[VideoCategory]" = video_category_list_response["items"]  # type: ignore

        categories: "dict[int, str]" = {}

        for category in category_list:
            category_id: int = int(category["id"])
            category_title: str = category["snippet"]["title"]

            categories[category_id] = category_title

        return categories[category_id]

    def _build_body(self, metadata: "MediaMetadata") -> dict:
        category_name: str = metadata.categories[0]
        category_id: int = self._get_category_id(category_name)

        body: dict = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": "public",
                "embeddable": True,
                # https://developers.google.com/youtube/v3/docs/videos/insert
                # can't make it public????? wtf???? thats bad
                "selfDeclaredMadeForKids": False
            }
        }

        assert body["status"]["privacyStatus"] in VALID_PRIVACY_STATUSES, "Invalid privacy status."  # future use

        return body

    def handle_upload(self, file: "ScratchFile", metadata: "MediaMetadata") -> "MediaMetadata | None":
        try:
            media_file_upload: "MediaFileUpload" = MediaFileUpload(
                str(file.path),
                chunksize=-1,
                resumable=True
            )

            videos_resource: "YouTubeResource.VideosResource" = self._youtube_oauth_resource.videos()

            body: dict = self._build_body(metadata)

            insert_request: "VideoHttpRequest" = videos_resource.insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media_file_upload
            )

            status, response = insert_request.next_chunk(num_retries=MAX_RETRIES)
            status: "None"
            response: "Video"

            logger.info(f"Successfully uploaded a YouTube video with ID {response['id']} "
                        f"from a source video with ID {metadata.id}.")

            return MediaMetadata(
                media_id=response["id"],
                platform=Platform.YOUTUBE,
                title=response["snippet"]["title"],
                description=response["snippet"]["description"],
                tags=response["snippet"].get("tags", []),  # sometimes not present
                categories=[self._get_category_name(int(response["snippet"].get("categoryId", "22")))],
                data=response["snippet"]
            )
        except HttpError as http_error:
            # todo: in case of a rate limit error, wait and retry
            logger.error(f"An HTTP error {http_error.resp.status} occurred:\n{http_error.content}")
            logger.exception(format_exc())
            return None
        finally:
            # the following cleanup calls aren't the most pythonic,
            # but they are easy to do and doing more would be hack and probably not worth the effort
            known_locals: "dict[str, Any]" = locals()
            if "media_file_upload" in known_locals:
                media_file_upload: "MediaFileUpload" = known_locals["media_file_upload"]
                media_stream: "IOBase" = media_file_upload.stream()  # type: ignore  # the stubs did this wrong
                if not media_stream.closed:
                    media_stream.close()


__all__: tuple[str] = (
    "YouTubeUploader",
    "YOUTUBE_UPLOAD_SCOPE"  # needed for the CLI
)
