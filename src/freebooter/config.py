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

from abc import ABCMeta
from os import environ
from typing import Generator, ClassVar

from tor_python_easy.tor_control_port_client import TorControlPortClient

from .middlewares import Middleware
from .uploaders import Uploader
from .watchers import Watcher


class Configuration(metaclass=ABCMeta):
    """
    An abstract class defining the configuration of freebooter.
    """

    TOR_PROXY_CLIENT: ClassVar[TorControlPortClient | None] = None

    def __init__(self) -> None:
        pass

    # Tor stuff
    @staticmethod
    def global_tor_host(cls) -> str | None:
        """
        Returns the global configuration.
        """
        return environ.get("FREEBOOTER_TOR_PROXY_HOST")

    @staticmethod
    def global_tor_port(cls) -> int | None:
        """
        Returns the global configuration.
        """
        return int(environ["FREEBOOTER_TOR_PROXY_PORT"]) if "FREEBOOTER_TOR_PROXY_PORT" in environ else None

    @staticmethod
    def global_tor_control_port(cls) -> int | None:
        """
        Returns the global configuration.
        """
        return (
            int(environ["FREEBOOTER_TOR_PROXY_CONTROL_PORT"])
            if "FREEBOOTER_TOR_PROXY_CONTROL_PORT" in environ
            else None
        )

    @staticmethod
    def global_tor_password(cls) -> str | None:
        """
        Returns the global configuration.
        """
        return environ.get("FREEBOOTER_TOR_PROXY_PASSWORD")

    @staticmethod
    def global_tor_proxy(cls) -> str | None:
        """
        Returns the global configuration.
        """
        host = cls.global_tor_host()
        port = cls.global_tor_port()

        if host is None or port is None:
            return None

        return f"socks5://{host}:{port}"

    @staticmethod
    def global_tor_proxy_client(cls) -> TorControlPortClient | None:
        """
        Returns the global configuration.
        """
        if cls.TOR_PROXY_CLIENT is not None:
            return cls.TOR_PROXY_CLIENT

        host = cls.global_tor_host()
        port = cls.global_tor_port()
        control_port = cls.global_tor_control_port()
        password = cls.global_tor_password()

        if host is None or port is None:
            return None

        if control_port is None:
            control_port = port + 1  # guessing

        cls.TOR_PROXY_CLIENT = TorControlPortClient(
            host,
            control_port,
            password,
        )

        return cls.TOR_PROXY_CLIENT

    # End tor stuff

    def watchers(self) -> Generator[Watcher, None, None]:
        """
        Returns a generator of watchers.
        """
        raise NotImplementedError

    def middlewares(self) -> Generator[Middleware, None, None]:
        """
        Returns a generator of middlewares.
        """
        raise NotImplementedError

    def uploaders(self) -> Generator[Uploader, None, None]:
        """
        Returns a generator of uploaders.
        """
        raise NotImplementedError


__all__ = ("Configuration",)
