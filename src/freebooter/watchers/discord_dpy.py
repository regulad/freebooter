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

from asyncio import Task, get_event_loop
from logging import WARNING, INFO, NullHandler
from typing import Any, AsyncGenerator, cast

import discord
from jishaku import Jishaku, Flags
from discord import Client, Intents, Message
from discord.ext.commands.bot import Bot
from jishaku.features.python import PythonFeature
from jishaku.repl import Scope

from .common import AsyncioWatcher
from ..middlewares import Middleware
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, Platform, MediaType

null_handler = NullHandler()
discord.utils.setup_logging(level=INFO if __debug__ else WARNING, root=False, handler=null_handler)


class DiscordPyWatcher(AsyncioWatcher):
    MYSQL_TYPE = "BIGINT UNSIGNED"

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        token: str,
        channels: list[int],
        discord_client_kwargs: dict[str, Any] | None = None,
        jishaku_prefix: str | None = "]",
        backtrack: int | None = 0,
        copy: bool = False,
        **config,
    ) -> None:
        """
        :param name: The name of the watcher.
        :param preprocessors: A list of middlewares to run before uploading.
        :param token: The token of the bot to use.
        :param channels: A list of channel IDs to watch.
        :param discord_client_kwargs: Additional kwargs to pass to the discord.Client constructor.
        :param jishaku_prefix: The prefix for Jishaku. If None, Jishaku will not be loaded, and the Discord client
        will not be a bot.
        :param backtrack: The amount of messages to backtrack, if any. If 0, no messages will be backtracked. If None, all messages will be backtracked.
        :param copy: Whether to copy the media if it is already handled.
        :param config: Additional configuration options.
        """
        super().__init__(name, preprocessors, **config)

        self._client: Client | None = None

        self._token = token
        self._channels: set[int] = set(channels)  # memory optimization
        self._discord_client_kwargs: dict[str, Any] = discord_client_kwargs or {}
        self._jishaku_prefix = jishaku_prefix

        self._backtrack = backtrack
        self._copy = copy

        self._discord_connection_task: Task | None = None
        self._backtrack_task: Task | None = None

    async def aclose(self) -> None:
        await super().aclose()
        if self._client is not None and not self._client.is_closed():
            if self._backtrack_task is not None:
                self._backtrack_task.cancel(msg="Watcher closing.")
            await self._client.close()
            if self._discord_connection_task is not None:
                await self._discord_connection_task  # let it finish

    async def medias_in_message(
        self, message: Message, *, handle_if_already_handled: bool = False
    ) -> AsyncGenerator[tuple[ScratchFile, MediaMetadata], None]:
        assert self._file_manager is not None, "File manager not set."

        for attachment in message.attachments:
            if not handle_if_already_handled and self.is_handled(attachment.id):
                continue

            scratch_file = self._file_manager.get_file(file_name=attachment.filename)

            await attachment.save(scratch_file.path)  # discord.py messed up the typing on this

            media_metadata = MediaMetadata(
                media_id=str(attachment.id),
                platform=Platform.DISCORD,
                title=attachment.filename,
                description=message.content,
                media_type=MediaType.from_file_path(scratch_file.path),
                data={"attachment": attachment.to_dict()},
            )

            yield scratch_file, media_metadata

            self.mark_handled(attachment.id)

    async def process_message(
        self, message: Message, *, handle_if_already_handled: bool = False
    ) -> list[MediaMetadata]:
        medias: list[tuple[ScratchFile, MediaMetadata]] = []

        async for scratch_file, media_metadata in self.medias_in_message(
            message, handle_if_already_handled=handle_if_already_handled
        ):
            medias.append((scratch_file, media_metadata))

        if medias:
            return await self._a_preprocess_and_execute(medias)
        else:
            return []

    async def on_message(self, message: Message) -> None:
        if message.channel.id in self._channels and message.attachments:
            self.logger.debug(f"Received message from {message.author} in {message.channel}.")
            medias = await self.process_message(message)
            self.logger.debug(
                f"Finished processing message from {message.author} in {message.channel}. With return {medias}."
            )

    async def backtrack(self) -> None:
        assert self._client is not None, "Client not set."

        await self._client.wait_until_ready()

        for channel_id in self._channels:
            channel = self._client.get_channel(channel_id)

            if channel is None:
                self.logger.warning(f"Channel {channel_id} not found.")
                continue

            if hasattr(channel, "history"):  # not all channel types have history
                async for message in channel.history(limit=self._backtrack, oldest_first=True):
                    if message.attachments:
                        await self.process_message(message, handle_if_already_handled=self._copy)

        if self._copy:
            self._copy = False

    async def async_prepare(self) -> None:
        await super().async_prepare()

        loop = self._loop or get_event_loop()

        intents = Intents.default()
        intents.message_content = True

        if self._jishaku_prefix is not None:
            self._client = Bot(
                command_prefix=self._jishaku_prefix,
                intents=intents,
                **self._discord_client_kwargs,
            )
            self._client.add_listener(self.on_message, "on_message")

            Flags.RETAIN = True

            await self._client.load_extension("jishaku")
            jishaku_cog: Jishaku = cast("Jishaku", self._client.get_cog("Jishaku"))

            python_feature: PythonFeature = cast("PythonFeature", jishaku_cog)
            scope: Scope = python_feature.scope

            scope.update_globals({f"{Flags.SCOPE_PREFIX}watcher": self})
        else:
            self._client = Client(intents=intents, **self._discord_client_kwargs)
            self._client.on_message = self.on_message  # type: ignore

        await self._client.login(self._token)
        self._discord_connection_task = loop.create_task(self._client.connect())

        self.logger.debug(f"{self.name} logged in to discord successfully.")

        if self._backtrack is None or self._backtrack > 0:
            self._backtrack_task = loop.create_task(self.backtrack())


__all__ = ("DiscordPyWatcher",)
