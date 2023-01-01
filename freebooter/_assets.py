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
from importlib.resources import files
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from importlib.abc import Traversable

# This file is currently unused. In the future, it will be used for the CLI/Docker interface validating files.

_PACKAGE_ROOT: "Traversable" = files("freebooter")  # may not be ideal?

ASSETS: "Traversable" = _PACKAGE_ROOT / "assets"

__all__: tuple[str] = (
    "ASSETS",
)
