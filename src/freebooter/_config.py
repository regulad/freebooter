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

import json
from functools import partial
from typing import Any, Type, Mapping, Generator

import jsonschema

from .config import Configuration
from ._assets import ASSETS
from .middlewares import Middleware, MetadataModifier, MediaCollector, Dropper
from .uploaders import (
    Uploader,
    InstagrapiUploader,
    YouTubeDataAPIV3Uploader,
    LocalMediaStorage,
    TweepyTwitterUploader,
)
from .util import FrozenDict
from .watchers import (
    Watcher,
    YTDLYouTubeChannelWatcher,
    Pusher,
    RSSWatcher,
    LocalMediaLoader,
    InstaloaderWatcher,
)

CONFIG_SCHEMA_TRAVERSABLE = ASSETS / "config-schema.json"

with CONFIG_SCHEMA_TRAVERSABLE.open(mode="r") as fp:
    CONFIG_SCHEMA = json.load(fp)


def check_config(config: dict[str, Any]) -> None:
    """
    Checks if the config is valid.
    """
    jsonschema.validate(config, CONFIG_SCHEMA)


MIDDLEWARES: Mapping[str, Type[Middleware]] = FrozenDict(
    {
        "metadata": MetadataModifier,
        "collector": MediaCollector,
        "dropper": Dropper,
    }
)

WATCHERS: Mapping[str, Type[Watcher]] = FrozenDict(
    {
        "youtube": YTDLYouTubeChannelWatcher,
        "rss": RSSWatcher.choose_best_watcher,  # type: ignore  # hacky but works fine
        "pusher": Pusher,
        "instagram": InstaloaderWatcher,
        "local": LocalMediaLoader,
    }
)

UPLOADERS: Mapping[str, Type[Uploader]] = FrozenDict(
    {
        "instagram": InstagrapiUploader,
        "youtube": YouTubeDataAPIV3Uploader,
        "local": LocalMediaStorage,
        "twitter": TweepyTwitterUploader,
    }
)


class LegacyYamlConfiguration(Configuration):
    # TODO: replace yaml configuration with MariaDB configuration
    """
    A concrete implementation of the Configuration interface.
    """
    watcher_cache: dict[str, Watcher] = {}
    uploader_cache: dict[str, Uploader] = {}
    middleware_cache: dict[str, Middleware] = {}

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self._config = config
        check_config(config)

    def _middleware_of(
        self, middleware_data: dict[str, Any], *, prepend_name: str = ""
    ) -> Middleware:
        middleware_cls: Type[Middleware] = MIDDLEWARES[middleware_data["type"]]

        if prepend_name:
            name = prepend_name + "-" + middleware_data["name"]
        else:
            name = middleware_data["name"]

        if name in self.middleware_cache:
            return self.middleware_cache[name]

        return middleware_cls(name, **middleware_data["config"])

    def _uploader_of(self, uploader_data: dict[str, Any]) -> Uploader:
        uploader_cls: Type[Uploader] = UPLOADERS[uploader_data["type"]]

        name = uploader_data["name"]

        if name in self.uploader_cache:
            return self.uploader_cache[name]

        preprocessors = [
            self._middleware_of(middleware, prepend_name=name)
            for middleware in uploader_data["preprocessors"]
        ]

        uploader = uploader_cls(name, preprocessors, **uploader_data["config"])

        self.uploader_cache[name] = uploader

        return uploader

    def _watcher_of(self, watcher_data: dict[str, Any]) -> Watcher:
        watcher_cls: Type[Watcher] = WATCHERS[watcher_data["type"]]

        name = watcher_data["name"]

        if name in self.watcher_cache:
            return self.watcher_cache[name]

        preprocessors = [
            self._middleware_of(middleware, prepend_name=name)
            for middleware in watcher_data["preprocessors"]
        ]

        watcher = watcher_cls(name, preprocessors, **watcher_data["config"])

        self.watcher_cache[name] = watcher

        return watcher

    def watchers(self) -> Generator[Watcher, None, None]:
        for watcher in self._config["watchers"]:
            yield self._watcher_of(watcher)

    def uploaders(self) -> Generator[Uploader, None, None]:
        for uploader in self._config["uploaders"]:
            yield self._uploader_of(uploader)

    def middlewares(self) -> Generator[Middleware, None, None]:
        for middleware in self._config["middlewares"]:
            yield self._middleware_of(middleware)


__all__ = ("LegacyYamlConfiguration",)
