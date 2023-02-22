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
import os
import sys
import time
import webbrowser
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, Future, Executor
from functools import partial
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
from threading import Event
from typing import cast, Any

import yaml
from dislog import DiscordWebhookHandler
from google_auth_oauthlib.flow import Flow
from jsonschema import validate, ValidationError
from mariadb import ConnectionPool
from oauthlib.oauth2 import OAuth2Token
from pillow_heif import register_heif_opener
from tweepy import OAuth1UserHandler

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


def authorize_twitter_api() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "--consumer-key",
        "-C",
        type=str,
        required=False,
        help="The consumer key for the Twitter API. If false, the Mac key will be used.",
    )
    parser.add_argument(
        "--consumer-secret",
        "-S",
        type=str,
        required=False,
        help="The consumer secret for the Twitter API. If false, the Mac key will be used.",
    )

    args = parser.parse_args()

    # run it!

    consumer_key = args.consumer_key or MAC_OAUTH_CONSUMER_KEY
    consumer_secret = args.consumer_secret or MAC_OAUTH_CONSUMER_SECRET

    oauth = OAuth1UserHandler(
        consumer_key=consumer_key, consumer_secret=consumer_secret, callback="oob"
    )

    url = oauth.get_authorization_url(signin_with_twitter=True)

    webbrowser.open(url)

    verifier = input(f"Enter the code you got from {url}: ")

    access_token, access_secret = oauth.get_access_token(verifier)

    print(f"Access token: {access_token}")
    print(f"Access secret: {access_secret}")


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

    logger.info("Logging configured successfully.")

    # setup folders

    logger.info("Setting up scratch folder and config folder...")

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

    logger.info("Scratch folder and config folder setup.")

    # Load MariaDB configuration

    db_host = environ.get("FREEBOOTER_MYSQL_HOST", "localhost")
    db_port = int(environ.get("FREEBOOTER_MYSQL_PORT", "3306"))
    db_database = environ.get("FREEBOOTER_MYSQL_DATABASE", "freebooter")
    db_user = environ.get("FREEBOOTER_MYSQL_USER", "freebooter")
    db_password = environ.get("FREEBOOTER_MYSQL_PASSWORD", "password")

    logger.info("MariaDB configuration loaded.")

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

    logger.info("Validating config...")

    CONFIG_SCHEMA_CHECK(config_data)

    logger.info("Config OK.")

    logger.info("Loading config...")

    config_middlewares, config_watchers, config_uploaders = load_config(config_data)

    # Now we start opening connections and running our code:

    # This is copied from threading.futures.ThreadPoolExecutor, but with a maximum of 64 instead of 32
    max_workers = min(64, (os.cpu_count() or 1) + 4)

    # MariaDB startup

    logger.info("Initializing MariaDB connection pool...")

    pool = ConnectionPool(
        host=db_host,
        port=db_port,
        user=db_user,
        database=db_database,
        password=db_password,
        pool_name="freebooter",
        pool_size=min(max(len(config_watchers), 5), 64),
    )

    logger.info("Done.")

    # get stuff ready for watchers
    shutdown_event = Event()

    def upload_handler(
        medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        logger.debug(f"Running middlewares on {len(medias)} files...")

        for middleware in config_middlewares:
            medias = middleware.process_many(medias)

        logger.debug(
            f"Middlewares were processed. Running uploaders on {len(medias)} files..."
        )

        out_medias: list[tuple[ScratchFile, MediaMetadata | None]] = []

        with ThreadPoolExecutor(
            max_workers=min(max_workers, len(config_uploaders))
        ) as upload_executor:
            uploader_futures: list[
                Future[list[tuple[ScratchFile, MediaMetadata | None]]]
            ] = []
            for uploader in config_uploaders:
                uploader_futures.append(
                    upload_executor.submit(uploader.upload_and_preprocess, medias)
                )
            for future in uploader_futures:
                out_medias.extend(future.result())

        logger.debug(f"Uploaders were processed. Returning {len(out_medias)} files...")

        return out_medias

    def callback(
        medias: list[tuple[ScratchFile, MediaMetadata]],
        *,
        executor: Executor,
    ) -> Future[list[tuple[ScratchFile, MediaMetadata | None]]]:
        return executor.submit(upload_handler, medias)

    with ThreadPoolExecutor(
        thread_name_prefix="Uploader", max_workers=max_workers
    ) as callback_executor:
        # Preparing
        prepare_kwargs = {
            # Defaults
            "shutdown_event": shutdown_event,
            "file_manager": file_manager,
            "callback": partial(callback, executor=callback_executor),
            "pool": pool,
            # For special use cases
            "uploaders": config_uploaders,
            "middlewares": config_middlewares,
            "watchers": config_watchers,
        }

        total_items_to_prepare = (
            len(config_uploaders) + len(config_middlewares) + len(config_watchers)
        )
        prepare_workers_needed = min(max_workers, total_items_to_prepare)

        with ThreadPoolExecutor(
            thread_name_prefix="Setup", max_workers=prepare_workers_needed
        ) as setup_executor:
            logger.info("Preparing...")
            setup_futures: list[Future[None]] = []
            for uploader in config_uploaders:
                future = setup_executor.submit(uploader.prepare, **prepare_kwargs)
                setup_futures.append(future)
            for middleware in config_middlewares:
                future = setup_executor.submit(middleware.prepare, **prepare_kwargs)
                setup_futures.append(future)
            for watcher in config_watchers:
                future = setup_executor.submit(watcher.prepare, **prepare_kwargs)
                setup_futures.append(future)
            for future in setup_futures:
                future.result()
            logger.info("Done.")

        # Start watchers
        logger.info("Starting watchers...")
        for watcher in config_watchers:
            watcher.start()
        logger.info("Done.")

        try:
            if os.name == "nt":
                # Windows doesn't wait on this event correctly, so we have to do it ourselves
                while not shutdown_event.is_set():
                    time.sleep(1)
            else:
                shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down...")
            shutdown_event.set()

        logger.info("Closing watchers...")
        for watcher in config_watchers:
            watcher.close()
        logger.info("Done.")

    # Wait until after the executor shutdown is set to close the middlewares and uploaders as they may still be needed

    logger.info("Closing middlewares...")
    for middleware in config_middlewares:
        middleware.close()
    logger.info("Done.")

    logger.info("Closing uploaders...")
    for uploader in config_uploaders:
        uploader.close()
    logger.info("Done.")

    logger.info("Closing MariaDB connection pool...")
    pool.close()
    logger.info("Done.")

    logger.info("Closing file manager...")
    file_manager.close()
    logger.info("Done.")

    logger.info("Done. Exiting.")


if __name__ == "__main__":
    main()

__all__ = ("main", "authorize_youtube_data_api", "authorize_twitter_api")
