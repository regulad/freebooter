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
from typing import TypedDict


# I don't particularly like this. This is for typing only.

class OAuth2Token(TypedDict):
    access_token: str
    expires_in: int
    refresh_token: str
    scope: list[str]
    token_type: str
    expires_at: float


class ClientSecretSet(TypedDict):
    client_id: str
    client_secret: str
    redirect_uris: list[str]
    auth_uri: str
    token_uri: str


class DesktopAppClientSecrets(TypedDict):
    installed: ClientSecretSet


__all__: tuple[str] = (
    "OAuth2Token",
    "ClientSecretSet",
    "DesktopAppClientSecrets",
)
