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

import datetime
import re
import time
import typing
from threading import Lock
from typing import Any, Literal

from PIL import Image
from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ReloginAttemptExceeded,
    LoginRequired,
    ChallengeRequired,
    SelectContactPointRecoveryForm,
    RecaptchaChallengeForm,
    FeedbackRequired,
    PleaseWaitFewMinutes,
    ClientError,
)
from instagrapi.types import Media as InstagramMedia, Story
from instagrapi.utils import json_value
from pyotp import TOTP
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from .common import Uploader
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, MediaType, Platform
from ..middlewares import Middleware


class InstagrapiUploader(Uploader):
    """
    Uploads media to Instagram using the instagrapi library.
    """

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        # Instagrapi client settings
        username: str,
        password: str,
        otp: str | None = None,
        proxy: str | None = None,
        delay_start: int | None = None,
        delay_end: int | None = None,
        insta_settings: dict[str, Any] | None = None,
        insta_kwargs: dict[str, Any] | None = None,
        retry_count: int = 5,
        # Uploader settings
        mode: Literal["singleton", "story", "album", "reels", "igtv"] = "singleton",
        **config,
    ) -> None:
        """
        :param name: The name of the uploader.
        :param preprocessors: A list of preprocessors to run before uploading.
        :param username: The username of the Instagram account to upload to. :param password: The password of the
        Instagram account to upload to.
        :param otp: The secret for the two-factor authentication of the
        Instagram account to upload to.
        :param proxy: The proxy to use for the upload. This should be in the format
        of "http://user:pass@host:port". This is recommended if you are uploading from a VPS or other datacenter IP.
        :param delay_start: The minimum delay to use between requests. This is used to prevent Instagram from
        blocking your account.
        :param delay_end: The maximum delay to use between requests. This is used to prevent Instagram from
        blocking your account.
        :param insta_settings: A dictionary of settings to pass to the instagrapi client.
        See the instagrapi documentation.
        :param insta_kwargs: A dictionary of keyword arguments to pass to the instagrapi client.
        See the instagrapi documentation.
        :param retry_count: The number of times to retry a request before giving up.
        :param mode: The mode to use for the upload. This can be one of the following: "singleton" - Uploads the
        file as a single post. "story" - Uploads the file as a story. "album" - Uploads the file as an album.
        "reels" - Uploads the file as a reels post. "igtv" - Uploads the file as an IGTV video.
        :param config: Additional configuration options for the uploader.
        """
        super().__init__(name, preprocessors, **config)

        delay: list[int] | None
        if delay_start is not None and delay_end is not None:
            delay = [delay_start, delay_end]
        else:
            delay = None

        # for typing
        insta_settings_nonnull: dict[str, Any] = insta_settings or {}
        insta_kwargs_nonnull: dict[str, Any] = insta_kwargs or {}

        insta_settings_nonnull.setdefault("country", "US")
        insta_settings_nonnull.setdefault("locale", "en_US")
        insta_settings_nonnull.setdefault("country_code", 1)

        # time handling, which is "nice" in python
        if "timezone_offset" not in insta_settings_nonnull:
            now = datetime.datetime.now()
            timezone = now.astimezone().tzinfo

            assert timezone is not None, "Timezone is None"

            utc_timedelta = timezone.utcoffset(now)

            assert utc_timedelta is not None, "UTC timedelta is None"

            timezone_offset_seconds = utc_timedelta.total_seconds()

            insta_settings_nonnull["timezone_offset"] = int(timezone_offset_seconds)

        # settings are used by instagrapi.mixins.LoginMixin
        self._iclient = Client(
            settings=insta_settings_nonnull,
            proxy=proxy,
            delay_range=delay,
            logger=self.logger,
            **insta_kwargs_nonnull,
        )

        # Setup retry adapter
        # This could cause problems when the Instagrapi client fails over and trys to reauth/whatever, but I don't
        # think it's a problem.
        retry = Retry.from_int(retry_count)
        retry_adapter = HTTPAdapter(max_retries=retry)
        self._iclient.public.mount("http://", retry_adapter)
        self._iclient.public.mount("https://", retry_adapter)
        self._iclient.private.mount("http://", retry_adapter)
        self._iclient.private.mount("https://", retry_adapter)

        # Error handling

        # For methods that are not implemented in the public version of instagrapi, I commented them out and replaced
        # them with pass for future reimplementation.
        # Freeze has been replaced with a simple sleep.
        self._iclient_exception = Lock()
        self._sleeping_until: datetime.datetime | None = None

        def freeze(
            reason: str, unfreeze_at: datetime.datetime | None = None, **kwargs: Any
        ) -> None:
            assert self._sleeping_until is None, "Already sleeping!"

            time_now = datetime.datetime.now()
            if unfreeze_at is None:
                delta = datetime.timedelta(**kwargs)
                unfreeze_at = time_now + delta

            assert unfreeze_at is not None, "unfreeze_at is None"

            self._sleeping_until = unfreeze_at

            # BLOCKING
            until_delta = unfreeze_at - time_now
            self.logger.warning(
                f'Freezing for "{reason}" until {unfreeze_at}! ({until_delta})'
            )
            sleep_for_seconds = max(until_delta.total_seconds(), 0)  # can't be under 0
            time.sleep(sleep_for_seconds)

            self._sleeping_until = None

        @typing.no_type_check  # from instagrapi, which is not typed
        def handle_exception(client: Client, e: ClientError) -> None:
            with self._iclient_exception:
                if isinstance(e, BadPassword):
                    client.logger.exception(e)
                    pass  # client.set_proxy(self.next_proxy().href)
                    if client.relogin_attempt > 0:
                        freeze(str(e), days=7)
                        raise ReloginAttemptExceeded(e)
                    pass  # client.settings = self.rebuild_client_settings()
                    return  # return self.update_client_settings(client.get_settings())
                elif isinstance(e, LoginRequired):
                    client.logger.exception(e)
                    client.relogin()
                    return  # return self.update_client_settings(client.get_settings())
                elif isinstance(e, ChallengeRequired):
                    api_path = json_value(client.last_json, "challenge", "api_path")
                    if api_path == "/challenge/":
                        pass  # client.set_proxy(self.next_proxy().href)
                        pass  # client.settings = self.rebuild_client_settings()
                    else:
                        try:
                            client.challenge_resolve(client.last_json)
                        except ChallengeRequired as e:
                            freeze("Manual Challenge Required", days=2)
                            raise e
                        except (
                            ChallengeRequired,
                            SelectContactPointRecoveryForm,
                            RecaptchaChallengeForm,
                        ) as e:
                            freeze(str(e), days=4)
                            raise e
                        pass  # self.update_client_settings(client.get_settings())
                    return  # True
                elif isinstance(e, FeedbackRequired):
                    message = client.last_json["feedback_message"]
                    if "This action was blocked. Please try again later" in message:
                        freeze(
                            message, hours=6
                        )  # this must have been meant to be 6 hours
                        # client.settings = self.rebuild_client_settings()
                        # return self.update_client_settings(client.get_settings())
                    elif (
                        "We restrict certain activity to protect our community"
                        in message
                    ):
                        # 6 hours is not enough
                        freeze(message, hours=12)
                    elif "Your account has been temporarily blocked" in message:
                        """
                        Based on previous use of this feature, your account has been temporarily
                        blocked from taking this action.
                        This block will expire on 2020-03-27.
                        """
                        yyyy_mm_dd = re.search(r"on (\d{4}-\d{2}-\d{2})", message)
                        unfreeze_at = datetime.datetime.strptime(
                            yyyy_mm_dd.group(1), "%Y-%m-%d"
                        )
                        freeze(message, unfreeze_at=unfreeze_at)
                elif isinstance(e, PleaseWaitFewMinutes):
                    freeze(str(e), hours=1)
                raise e

        self._iclient.handle_exception = handle_exception

        # 2FA / OTP handling
        self._otp: TOTP | None = TOTP(otp) if otp else None

        # Why we need to do this:
        #     instagrapi does not properly use the one-time password (2FA) when relogging in.
        # OTPs currently do not work in instagrapi, so this is useless for now.
        # Issue: https://github.com/adw0rd/instagrapi/issues/1042
        if self._otp:
            iclient_login_bound_method = self._iclient.login

            def better_login(*args, **kwargs) -> bool:
                assert self._otp is not None, "OTP is None"
                kwargs.setdefault("verification_code", self._otp.now())
                return iclient_login_bound_method(*args, **kwargs)

            self._iclient.login = better_login

        # Login
        if username is None or password is None:
            raise RuntimeError("Instagram username and password must be provided!")

        self.logger.info(
            "Logging in to Instagram for the first time, this may take a while..."
        )
        instagram_login_success = self._iclient.login(username, password)

        if not instagram_login_success:
            raise RuntimeError("Failed to login to Instagram!")

        # Watcher Configuration
        self._mode = mode

    def background_task(self) -> None:
        if self._iclient_exception.locked() and self._sleeping_until is not None:
            self.logger.warning(
                f"Instagram client is locked out! Sleeping until {self._sleeping_until}"
            )

    def upload(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        assert self._file_manager is not None, "FileManager is None"

        instagram_medias: list[tuple[ScratchFile, InstagramMedia | Story | None]] = []

        match self._mode:
            case "singleton" | "reels":
                for media, metadata in medias:
                    try:
                        match metadata.type:
                            case MediaType.PHOTO:
                                file_extension = media.path.suffix

                                # this is not the most reliable way of detecting file types, but ffprobe is weird man
                                if file_extension == ".gif":
                                    # Instagram doesn't like gifs.
                                    # We will need to do some special handling to extract the first frame.

                                    with self._file_manager.get_file(
                                        file_extension=".jpg"
                                    ) as temp_file:
                                        with Image.open(media.path) as gif:
                                            gif.seek(0)
                                            with gif.convert("RGB") as image:
                                                image.save(temp_file.path, "JPEG")

                                        instagram_medias.append(
                                            (
                                                media,
                                                self._iclient.photo_upload(
                                                    temp_file.path, metadata.description
                                                ),
                                            )
                                        )
                                elif file_extension not in [".jpg", ".jpeg"]:
                                    # e.g. .tiff .webp

                                    # Instagram doesn't like non-jpg images. We need to convert them to jpegs.
                                    # Instagram says that it can handle PNG, but I couldn't get it to work.
                                    # Same goes for HEIC/HEIF.

                                    with self._file_manager.get_file(
                                        file_extension=".jpg"
                                    ) as temp_file:
                                        with Image.open(
                                            media.path
                                        ) as image, image.convert("RGB") as rgb_image:
                                            rgb_image.save(temp_file.path, "JPEG")

                                        instagram_medias.append(
                                            (
                                                media,
                                                self._iclient.photo_upload(
                                                    temp_file.path, metadata.description
                                                ),
                                            )
                                        )
                                else:
                                    instagram_medias.append(
                                        (
                                            media,
                                            self._iclient.photo_upload(
                                                media.path, metadata.description
                                            ),
                                        )
                                    )
                            case MediaType.VIDEO:
                                instagram_medias.append(
                                    (
                                        media,
                                        self._iclient.video_upload(
                                            media.path, metadata.description
                                        ),
                                    )
                                )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to upload {media.path} to Instagram: {e}"
                        )
                        instagram_medias.append((media, None))
                        continue
            case "story":
                for media, metadata in medias:
                    try:
                        match metadata.type:
                            case MediaType.PHOTO:
                                instagram_medias.append(
                                    (
                                        media,
                                        self._iclient.photo_upload_to_story(media.path),
                                    )
                                )
                            case MediaType.VIDEO:
                                instagram_medias.append(
                                    (
                                        media,
                                        self._iclient.video_upload_to_story(media.path),
                                    )
                                )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to upload {media.path} to Instagram: {e}"
                        )
                        instagram_medias.append((media, None))
                        continue
            case "album":
                if len(medias) > 10:
                    raise ValueError("Instagram only supports 10 photos per album!")
                elif len(medias) < 2:
                    raise ValueError("Instagram requires at least 2 photos per album!")

                try:
                    instagram_media = self._iclient.album_upload(
                        [media.path for media, _ in medias], medias[0][1].description
                    )
                except Exception as e:
                    self.logger.error(f"Failed to upload album to Instagram: {e}")
                    instagram_medias.extend((media, None) for media, _ in medias)
                else:
                    for media, metadata in medias:
                        instagram_medias.append((media, instagram_media))
            case "igtv":
                for media, metadata in medias:
                    try:
                        instagram_medias.append(
                            (
                                media,
                                self._iclient.igtv_upload(
                                    media.path,
                                    metadata.title or "IGTV Video",
                                    metadata.description,
                                ),
                            )
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to upload {media.path} to Instagram: {e}"
                        )
                        instagram_medias.append((media, None))
                        continue

        return_medias: list[tuple[ScratchFile, MediaMetadata | None]] = []

        for media, instagram_media in instagram_medias:
            freebooter_metadata: MediaMetadata | None = None
            url: str | None = None
            if isinstance(instagram_media, InstagramMedia):
                freebooter_metadata = MediaMetadata(
                    media_id=instagram_media.id,
                    platform=Platform.INSTAGRAM,
                    title=instagram_media.title,
                    description=instagram_media.caption_text,
                    tags=[],
                    categories=[],
                    media_type=MediaType.PHOTO
                    if instagram_media.media_type == 1
                    else MediaType.VIDEO,
                    data=instagram_media.dict(),
                )
                url = f"https://www.instagram.com/p/{instagram_media.code}/"
            elif isinstance(instagram_media, Story):
                freebooter_metadata = MediaMetadata(
                    media_id=instagram_media.id,
                    platform=Platform.INSTAGRAM,
                    title=None,
                    description=None,
                    tags=[],
                    categories=[],
                    media_type=MediaType.PHOTO
                    if instagram_media.media_type == 1
                    else MediaType.VIDEO,
                    data=instagram_media.dict(),
                )

            self.logger.info(f"Uploaded {media.path} to Instagram at {url}")
            return_medias.append((media, freebooter_metadata))

        return return_medias


__all__ = ("InstagrapiUploader",)
