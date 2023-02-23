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

import random
from datetime import datetime
from typing import Generator

import discord
from discord import SyncWebhook, SyncWebhookMessage, Embed, Color
from discord.utils import MISSING
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from .common import Uploader
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, Platform
from ..middlewares import Middleware


class DiscordWebhookUploader(Uploader):
    """
    Uploads content to a Discord webhook.
    """

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        webhook: str,
        bot_token: str | None = None,
        proxies: dict[str, str] | None = None,
        retry_count: int = 3,
        **config,
    ) -> None:
        """
        :param name: The name of the uploader.
        :param preprocessors: A list of middlewares to run before uploading.
        :param webhook_url: The URL of the webhook to upload to.
        :param bot_token: The bot token to use for the webhook. Optional.
        :param proxies: A dictionary of proxies to use for the webhook. Optional.
        :param retry_count: The number of times to retry the upload. Defaults to 3.
        :param config: Additional configuration options.
        """
        super().__init__(name, preprocessors, **config)

        self._webhook_url = webhook
        self._token = bot_token

        self._session = Session()

        if retry_count > 0:
            retry = Retry.from_int(retry_count)
            retry_adapter = HTTPAdapter(max_retries=retry)
            self._session.mount("https://", retry_adapter)
            self._session.mount("http://", retry_adapter)

        if proxies is not None:
            self._session.proxies |= proxies

        self._webhook = SyncWebhook.from_url(
            self._webhook_url, session=self._session, bot_token=self._token
        )

    def upload_generator(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> Generator[tuple[ScratchFile, MediaMetadata | None], None, None]:
        for media in medias:
            file, metadata = media

            with file.open("r") as fp:
                discord_file = discord.File(  # type: ignore
                    fp,  # type: ignore
                    filename=file.path.name,
                    description=metadata.description,
                )

                embed: Embed | None = (
                    (
                        Embed(
                            title=metadata.title,
                            description=metadata.description,
                            color=Color(random.randint(0, 0xFFFFFF)),
                            timestamp=datetime.now(),
                        )
                        .set_image(url="attachment://" + file.path.name)
                        .set_footer(text=f"From {metadata.platform.name.title()}")
                    )
                    if metadata.title or metadata.description
                    else None
                )

                sync_webhook_message = self._webhook.send(
                    content=(metadata.title if embed is None else None) or MISSING,
                    file=discord_file,
                    wait=True,
                    embed=embed or MISSING,
                )

                assert isinstance(
                    sync_webhook_message, SyncWebhookMessage
                ), "SyncWebhookMessage is not a SyncWebhookMessage"

                ret_metadata = MediaMetadata(
                    media_id=str(sync_webhook_message.id), platform=Platform.DISCORD
                )

            yield file, ret_metadata

    def upload(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        return list(self.upload_generator(medias))


__all__ = ("DiscordWebhookUploader",)
