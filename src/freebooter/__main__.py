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
import sys
import webbrowser
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, Future
from io import FileIO
from logging import (
    basicConfig,
    DEBUG,
    INFO,
    Logger,
    getLogger,
    StreamHandler,
    ERROR,
)
from os import environ
from os.path import splitext
from pathlib import Path
from typing import cast

import yaml
from dislog import DiscordWebhookHandler
from google_auth_oauthlib.flow import Flow
from jsonschema import validate, ValidationError
from oauthlib.oauth2 import OAuth2Token
from pillow_heif import register_heif_opener

from . import *
from ._assets import *
from ._config import *
from .util import (
    Loader,
)  # Using a loader that supports !include makes our config files much more readable.

logger: Logger = getLogger(__name__)
rootLogger = Logger.root

# Init helper libraries
register_heif_opener()  # Enables Pillow to open HEIF files


def authorize_youtube_data_api() -> None:
    """
    Authorizes the user for the YouTube Data API v3.
    """

    parser = ArgumentParser()
    parser.add_argument(
        "--client-secret-path",
        "-C",
        type=str,
        required=True,
        help="Path to the client secret JSON file.",
    )
    parser.add_argument(
        "--oauth2-token-path",
        "-O",
        type=str,
        required=False,
        help="Path where the OAuth token will be stored. Defaults to the client secret path + '.oauth2'.",
    )

    # start

    args = parser.parse_args()

    # run

    client_secret_path = Path(args.client_secret_path)
    if not client_secret_path.exists():
        print(f"Client secret file {client_secret_path} does not exist.")
        sys.exit(1)

    if args.oauth2_token_path is None:
        oauth2_token_path = client_secret_path.with_suffix(".oauth2.json")
    else:
        oauth2_token_path = Path(args.oauth2_token_path)

    if oauth2_token_path.exists():
        print(f"Found OAuth2 token file {oauth2_token_path}, skipping authorization.")
        return

    # Check the config folder for valid files

    print("Checking validity of client secret...")

    with (ASSETS / "client-secret-schema.json").open("r") as schema_fp:
        client_secret_schema = json.load(schema_fp)

    with client_secret_path.open("r") as secret_fp:
        client_secret = json.load(secret_fp)

    try:
        validate(instance=client_secret, schema=client_secret_schema)
    except ValidationError as e:
        print(f"Client secret {client_secret_path} is not valid: {e}")
        sys.exit(1)

    print("Done. Config files are valid, proceeding...")

    # OAuth2 authorization (CLI only)

    print("Starting OAuth2 authorization flow.")
    print(f"Found client secret file {client_secret_path}, attempting to authorize.")

    flow = Flow.from_client_secrets_file(
        str(client_secret_path),
        scopes=[YOUTUBE_UPLOAD_SCOPE],
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )

    # Tell the user to go to the authorization URL.
    auth_url, state = flow.authorization_url(prompt="consent")

    print(f"Please go to this URL: {auth_url}")
    webbrowser.open(auth_url)

    # The user will get an authorization code. This code is used to get the
    # access token.
    code: str = input("Enter the authorization code: ")
    token: OAuth2Token = flow.fetch_token(code=code)

    print(f"Successfully authorized {client_secret_path}.")

    # Save the credentials for production later

    with oauth2_token_path.open("w") as fp:
        json.dump(token, fp)

    print(f"Saved OAuth2 token to {oauth2_token_path}.")
    return


def main() -> None:
    # note: I would *love* to do this all with asyncio, but since literally EVERY SINGLE LIBRARY is blocking, it's only
    # going to be possible with a shitload of asyncio.to_thread calls or with threads, which is what I did here.

    # logging configuration
    standard_handler: StreamHandler = StreamHandler(sys.stdout)
    error_handler: StreamHandler = StreamHandler(sys.stderr)

    standard_handler.addFilter(
        lambda record: record.levelno < ERROR
    )  # keep errors to stderr
    error_handler.setLevel(ERROR)

    basicConfig(
        format="%(asctime)s\t%(levelname)s\t%(name)s@%(threadName)s: %(message)s",
        level=DEBUG if __debug__ else INFO,
        handlers=[standard_handler, error_handler],
    )

    dislog_url: str | None = environ.get("FREEBOOTER_DISCORD_WEBHOOK")

    if dislog_url is not None:
        logger.info("Discord Webhook provided, enabling Discord logging.")

        dislog_message: str | None = environ.get("FREEBOOTER_DISCORD_WEBHOOK_MESSAGE")

        handler = DiscordWebhookHandler(
            dislog_url,
            level=INFO,  # debug is just too much for discord to handle
            text_send_on_error=dislog_message,
        )
        rootLogger.addHandler(handler)

    # setup folders

    scratch_folder = Path(environ.get("FREEBOOTER_SCRATCH", "scratch"))

    if not scratch_folder.is_absolute():
        scratch_folder = scratch_folder.absolute()

    if not scratch_folder.exists():
        scratch_folder.mkdir(parents=True)
        logger.debug(f"Created scratch folder in {scratch_folder}")

    config_folder = Path(environ.get("FREEBOOTER_CONFIG", "config"))

    if not config_folder.is_absolute():
        config_folder = config_folder.absolute()

    if not config_folder.exists():
        config_folder.mkdir(parents=True)
        logger.debug(f"Created config folder in {config_folder}")

    file_manager = FileManager(scratch_folder)

    # MariaDB configuration

    db_host = environ.get("FREEBOOTER_MYSQL_HOST", "localhost")
    db_port = int(environ.get("FREEBOOTER_MYSQL_PORT", "3306"))
    db_database = environ.get("FREEBOOTER_MYSQL_DATABASE", "freebooter")
    db_user = environ.get("FREEBOOTER_MYSQL_USER", "freebooter")
    db_password = environ.get("FREEBOOTER_MYSQL_PASSWORD", "password")

    logger.info("Initializing MariaDB connection pool...")

    pool = ConnectionPool(
        host=db_host,
        port=db_port,
        database=db_database,
        user=db_user,
        password=db_password,
        pool_name="freebooter",
    )

    logger.info("MariaDB connection OK.")

    logger.info("Done.")

    # Load configuration

    config_location = environ.get("FREEBOOTER_CONFIG_FILE", "./config/config.yml")
    config_path = Path(config_location)

    if not config_path.is_absolute():
        config_path = config_path.absolute()

    if not config_path.exists():
        logger.error(f"Config file {config_path} does not exist.")
        sys.exit(1)

    config_data: Any

    with FileIO(config_path, "r") as config_file:
        config_file_name: Path = cast("Path", config_file.name)
        file_extension = splitext(config_file_name)[1]
        if file_extension == ".yml" or file_extension == ".yaml":
            config_data = yaml.load(config_file, Loader)
        else:
            config_data = json.load(config_file)

    # config loading/validation
    logger.info("Validating config...")

    CONFIG_SCHEMA_CHECK(config_data)

    logger.info("Config OK.")

    logger.info("Loading config...")

    config_middlewares, config_watchers, config_uploaders = load_config(config_data)

    # get stuff ready for watchers
    with ThreadPoolExecutor() as executor:  # easier to handle as context manager
        shutdown_event = Event()

        def upload_handler(
            medias: list[tuple[ScratchFile, MediaMetadata]]
        ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
            for middleware in config_middlewares:
                medias = middleware.process_many(medias)

            out_medias: list[tuple[ScratchFile, MediaMetadata | None]] = []

            uploader_futures: list[
                Future[list[tuple[ScratchFile, MediaMetadata | None]]]
            ] = []

            for uploader in config_uploaders:
                uploader_futures.append(
                    executor.submit(uploader.upload_and_preprocess, medias)
                )

            for future in uploader_futures:
                out_medias.extend(future.result())

            return out_medias

        def callback(
            medias: list[tuple[ScratchFile, MediaMetadata]]
        ) -> Future[list[tuple[ScratchFile, MediaMetadata | None]]]:
            return executor.submit(upload_handler, medias)

        logger.info("Done.")

        # Preparing
        logger.info("Preparing uploaders...")
        upload_prepare_futures: list[Future[None]] = []
        for uploader in config_uploaders:
            future = executor.submit(
                uploader.prepare,
                shutdown_event=shutdown_event,
                file_manager=file_manager,
            )
            upload_prepare_futures.append(future)
        for future in upload_prepare_futures:
            future.result()
        logger.info("Done.")

        logger.info("Preparing middlewares...")
        middleware_prepare_futures: list[Future[None]] = []
        for middleware in config_middlewares:
            future = executor.submit(
                middleware.prepare,
                shutdown_event=shutdown_event,
                file_manager=file_manager,
            )
            middleware_prepare_futures.append(future)
        for future in middleware_prepare_futures:
            future.result()
        logger.info("Done.")

        logger.info("Preparing watchers...")
        watcher_prepare_futures: list[Future[None]] = []
        for watcher in config_watchers:
            future = executor.submit(
                watcher.prepare,
                shutdown_event=shutdown_event,
                callback=callback,
                pool=pool,
                file_manager=file_manager,
            )
            watcher_prepare_futures.append(future)
        for future in watcher_prepare_futures:
            future.result()
        logger.info("Done.")

        # Start
        logger.info("Starting uploaders...")
        for uploader in config_uploaders:
            uploader.start()
        logger.info("Done.")

        logger.info("Starting middlewares...")
        for middleware in config_middlewares:
            middleware.start()
        logger.info("Done.")

        logger.info("Starting watchers...")
        for watcher in config_watchers:
            watcher.start()
        logger.info("Done.")

        try:
            shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down...")
            shutdown_event.set()

            logger.info("Waiting for watchers to finish...")
            for watcher in config_watchers:
                watcher.join()
                watcher.close()
            logger.info("Done.")

            logger.info("Waiting for middlewares to finish...")
            for middleware in config_middlewares:
                middleware.join()
                middleware.close()
            logger.info("Done.")

            logger.info("Waiting for uploaders to finish...")
            for uploader in config_uploaders:
                uploader.join()
                uploader.close()
            logger.info("Done.")

            logger.info("Closing MariaDB connection pool...")
            pool.close()
            logger.info("Done.")

            logger.info("Closing file manager...")
            file_manager.close()
            logger.info("Done.")

            logger.info("Done. Exiting.")
            return


if __name__ == "__main__":
    main()

__all__ = ("main", "authorize_youtube_data_api")
