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
from typing import Any, Type, Mapping

import jsonschema

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

SWAPPED_ORDER_VALIDATE = lambda schema, instance, *args, **kwargs: jsonschema.validate(
    instance, schema, *args, **kwargs
)  # noqa

CONFIG_SCHEMA_TRAVERSABLE = ASSETS / "config-schema.json"

with CONFIG_SCHEMA_TRAVERSABLE.open(mode="r") as fp:
    CONFIG_SCHEMA = json.load(fp)

CONFIG_SCHEMA_CHECK = partial(SWAPPED_ORDER_VALIDATE, CONFIG_SCHEMA)

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


def prepare_middleware(
    middleware_data: dict[str, Any], *, prepend_name: str = ""
) -> Middleware:
    middleware_cls: Type[Middleware] = MIDDLEWARES[middleware_data["type"]]
    return middleware_cls(
        prepend_name + middleware_data["name"], **middleware_data["config"]
    )


def load_config(config: Any) -> tuple[list[Middleware], list[Watcher], list[Uploader]]:
    assert isinstance(config, dict), "Config must be a dictionary!"
    assert CONFIG_SCHEMA_CHECK(config) is None, "Invalid config file!"

    middlewares = []
    watchers = []
    uploaders = []

    for middleware in config["middlewares"]:
        middlewares.append(prepare_middleware(middleware))

    for watcher in config["watchers"]:
        watcher_cls: Type[Watcher] = WATCHERS[watcher["type"]]

        preprocessors = [
            prepare_middleware(middleware, prepend_name=watcher["name"] + "-")
            for middleware in watcher["preprocessors"]
        ]

        watchers.append(
            watcher_cls(watcher["name"], preprocessors, **watcher["config"])
        )

    for uploader in config["uploaders"]:
        uploader_cls: Type[Uploader] = UPLOADERS[uploader["type"]]

        preprocessors = [
            prepare_middleware(middleware, prepend_name=uploader["name"] + "-")
            for middleware in uploader["preprocessors"]
        ]

        uploaders.append(
            uploader_cls(uploader["name"], preprocessors, **uploader["config"])
        )

    return middlewares, watchers, uploaders


__all__ = ("load_config", "CONFIG_SCHEMA_CHECK")
