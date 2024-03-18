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

import typing
from difflib import get_close_matches
from io import IOBase
from logging import getLogger
from threading import Lock
from traceback import format_exc
from typing import ClassVar
from typing import TYPE_CHECKING, cast
from typing import TypedDict

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, build_http
from httplib2 import Http
from oauthlib.oauth2 import (
    OAuth2Token,
)  # we don't actually use this type, but we use it as a NamedDict I mean WHATEVER

from .common import Uploader
from ..file_management import ScratchFile
from ..metadata import Platform, MediaMetadata, MediaType
from ..middlewares import Middleware

if TYPE_CHECKING:
    from googleapiclient._apis.youtube.v3.resources import (
        YouTubeResource,
        VideoHttpRequest,
        VideoCategoryListResponseHttpRequest,
        VideoCategoryListResponse,
        VideoCategory,
    )
    from googleapiclient._apis.youtube.v3.schemas import Video

logger = getLogger(__name__)

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


class ClientSecretSet(TypedDict):
    client_id: str
    client_secret: str
    redirect_uris: list[str]
    auth_uri: str
    token_uri: str


class DesktopAppClientSecrets(TypedDict):
    installed: ClientSecretSet


class YouTubeDataAPIV3Uploader(Uploader):
    """
    Uploads content to YouTube using the YouTube Data API v3.
    """

    glock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        client_secret_data: DesktopAppClientSecrets,
        oauth2_token_data: OAuth2Token,
        youtube_api_key: str,
        **config,
    ) -> None:
        super().__init__(name, preprocessors, **config)

        self._http_handler: Http = build_http()

        self._credentials = Credentials(
            token=oauth2_token_data["access_token"],
            refresh_token=oauth2_token_data["refresh_token"],
            token_uri=client_secret_data["installed"]["token_uri"],
            client_id=client_secret_data["installed"]["client_id"],
            client_secret=client_secret_data["installed"]["client_secret"],
            scopes=oauth2_token_data["scope"],
            # off by default for some reason
            enable_reauth_refresh=True,
        )

        self._youtube_oauth_resource: YouTubeResource = cast(
            "YoutubeResource",  # type: ignore  # breaks mypy
            build(  # type: ignore
                YOUTUBE_API_SERVICE_NAME,
                YOUTUBE_API_VERSION,
                credentials=self._credentials,
                http=self._http_handler,
            ),
        )
        self._youtube_dev_key_resource: YouTubeResource = cast(
            "YoutubeResource",  # type: ignore  # breaks mypy
            build(  # type: ignore
                YOUTUBE_API_SERVICE_NAME,
                YOUTUBE_API_VERSION,
                developerKey=youtube_api_key,
                http=self._http_handler,
            ),
        )

    def close(self) -> None:
        super().close()
        self._http_handler.close()
        del self._credentials  # does not close?

    def _get_category_id_by_name(self, category_name: str) -> int:
        """
        Returns the closest matching category ID for the given category name.
        :param category_name: The name of the category to get the ID for.
        :return: Category ID, or 22 (People & Blogs) if no match is found.
        """
        video_categories_resource: YouTubeResource.VideoCategoriesResource = (
            self._youtube_dev_key_resource.videoCategories()
        )
        video_categories_http_request: VideoCategoryListResponseHttpRequest = video_categories_resource.list(
            regionCode="US", part="snippet"
        )
        video_category_list_response: VideoCategoryListResponse = video_categories_http_request.execute(
            num_retries=MAX_RETRIES
        )
        category_list: list[VideoCategory] = video_category_list_response["items"]

        safe_categories: dict[str, int] = {}

        for category in category_list:
            if category["snippet"]["assignable"]:
                category_id = int(category["id"])
                category_title = category["snippet"]["title"]

                safe_categories[category_title] = category_id
            else:
                continue  # we can't assign it, so we might as well skip it

        close_matches: list[int] = [
            safe_categories[str(match)] for match in get_close_matches(category_name, safe_categories.keys())
        ]

        if len(close_matches) == 0:
            return 22  # we tried
        else:
            return close_matches[0]

    def _get_category_name_by_id(self, category_id: int) -> str | None:
        video_categories_resource: YouTubeResource.VideoCategoriesResource = (
            self._youtube_dev_key_resource.videoCategories()
        )
        video_categories_http_request: VideoCategoryListResponseHttpRequest = video_categories_resource.list(
            regionCode="US", part="snippet"
        )
        video_category_list_response: VideoCategoryListResponse = video_categories_http_request.execute(
            num_retries=MAX_RETRIES
        )
        category_list: list[VideoCategory] = video_category_list_response["items"]

        for category in category_list:
            category_id_from_list: int = int(category["id"])
            category_title_from_list: str = category["snippet"]["title"]

            if category_id_from_list == category_id:
                return category_title_from_list
        else:
            return None

    def _build_body(self, metadata: MediaMetadata) -> Video:
        category_name: str = metadata.categories[0]
        category_id: int = self._get_category_id_by_name(category_name)

        body: Video = {
            "snippet": {
                "title": metadata.title or "Untitled",
                "description": metadata.description or "",
                "tags": metadata.tags,
                "categoryId": str(category_id),
            },
            "status": {
                "privacyStatus": "public",
                "embeddable": True,
                # https://developers.google.com/youtube/v3/docs/videos/insert
                # can't make it public????? wtf???? thats bad
                "selfDeclaredMadeForKids": False,
            },
        }

        assert body["status"]["privacyStatus"] in VALID_PRIVACY_STATUSES, "Invalid privacy status."  # future use

        return body

    @typing.no_type_check  # mypy gets the list comp VERY wrong
    def upload(self, medias: list[tuple[ScratchFile, MediaMetadata]]) -> list[tuple[ScratchFile, MediaMetadata]]:
        return [
            uploaded
            for uploaded in [(file, self._upload_one(file, metadata)) for file, metadata in medias]
            if uploaded[1] is not None
        ]

    def _upload_one(self, file: ScratchFile, metadata: MediaMetadata) -> MediaMetadata | None:
        media_file_upload: MediaFileUpload = MediaFileUpload(str(file.path), chunksize=-1, resumable=True)
        try:
            videos_resource: YouTubeResource.VideosResource = self._youtube_oauth_resource.videos()

            body: Video = self._build_body(metadata)

            insert_request: VideoHttpRequest = videos_resource.insert(
                part=",".join(body.keys()), body=body, media_body=media_file_upload
            )

            status, response = insert_request.next_chunk(num_retries=MAX_RETRIES)  # type: None, Video

            logger.info(
                f"Successfully uploaded a YouTube video with ID {response['id']} "
                f"from a source video with ID {metadata.id}."
            )

            category_name = self._get_category_name_by_id(int(response["snippet"].get("categoryId", "22")))

            return MediaMetadata(
                media_id=response["id"],
                platform=Platform.YOUTUBE,
                title=response["snippet"]["title"],
                description=response["snippet"]["description"],
                tags=response["snippet"].get("tags", []),  # sometimes not present
                categories=[category_name] if category_name else [],
                data=cast(dict, response["snippet"]),
                media_type=MediaType.VIDEO,
            )
        except HttpError as http_error:
            logger.error(f"An HTTP error {http_error.resp.status} occurred:\n{http_error.content}")
            logger.exception(format_exc())
            return None
        finally:
            media_stream: IOBase = cast("IOBase", media_file_upload.stream())
            if not media_stream.closed:
                media_stream.close()


__all__ = ("YouTubeDataAPIV3Uploader", "YOUTUBE_UPLOAD_SCOPE")
