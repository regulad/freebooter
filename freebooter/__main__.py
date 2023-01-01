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
import json
import sys
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from logging import basicConfig, DEBUG, INFO, root as rootLogger, getLogger, StreamHandler, ERROR
from os import environ
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from dislog import DiscordWebhookHandler
from google_auth_oauthlib.flow import Flow
from jsonschema.validators import validate
from mariadb import ConnectionPool

from . import *
from ._assets import ASSETS

if TYPE_CHECKING:
    from argparse import Namespace
    from concurrent.futures import Future
    from logging import Logger
    from importlib.abc import Traversable

    from oauthlib.oauth2 import OAuth2Token

logger: "Logger" = getLogger(__name__)


def main() -> None:
    """
    The main function of the freebooter program.
    :return:
    """

    # arguments

    parser: "ArgumentParser" = ArgumentParser(
        prog="freebooter",
        description="freebooter downloads videos from a YouTube channels after they are uploaded "
                    "and uploads them onto your own YouTube channel.",
    )
    # MariaDB arguments
    parser.add_argument("--db-host", dest="db_host", type=str, required=False, help="The host of the MariaDB server.")
    parser.add_argument("--db-port", dest="db_port", type=int, required=False, help="The port of the MariaDB server.")
    parser.add_argument("--db-database", dest="db_database", type=str, required=False,
                        help="The name of the MariaDB database to connect to.")
    parser.add_argument("--db-user", dest="db_user", type=str, required=False, help="The username of the MariaDB user.")
    parser.add_argument("--db-password", dest="db_password", type=str, required=False,
                        help="The password of the MariaDB user.")
    # Freebooter arguments
    parser.add_argument("-i", "--in-channel", dest="in_channels", required=False, action="append",
                        help="The YouTube Channel IDs to download videos from.")
    parser.add_argument("-o", "--out-channel", dest="out_channels", required=False, action="append",
                        help="The YouTube Data API keys to upload videos to.")

    parser.add_argument("-C", "--config", dest="config", required=False, type=str,
                        help="The path to the config folder.")
    parser.add_argument("-s", "--scratch", dest="scratch", required=False, type=str,
                        help="The path to be the scratch/cache folder.")

    parser.add_argument("-c", "--copy", dest="copy", default=False, action="store_true",
                        help="Copy the videos of a channel instead of watching for them")

    parser.add_argument("-v", "--verbose", dest="verbose", default=False, action="store_true",
                        help="Enable verbose logging.")

    parser.add_argument("-w", "--discord-webhook", dest="discord_webhook", required=False, type=str,
                        help="A Discord webhook to send messages to.")

    parser.add_argument("-a", "--authorize-oauth2", dest="authorize_oauth2", default=False, action="store_true",
                        help="Starts a flow to authorize the OAuth2 credentials.")

    parser.add_argument("-y", "--youtube-api-key", dest="youtube_api_key", required=False, type=str,
                        help="The YouTube Data API key to use.")

    args: "Namespace" = parser.parse_args()

    # Global API Keys

    youtube_api_key: str | None = args.youtube_api_key or environ.get("FREEBOOTER_YOUTUBE_API_KEY")

    if youtube_api_key is None:
        logger.warning("No YouTube API key was provided. The YouTube Data API uploader will not work.")
    else:
        logger.info("YouTube API key was provided, enabling the YouTube Data API uploader.")

    # logging configuration

    debug: bool = args.verbose or environ.get("FREEBOOTER_DEBUG", "false").lower() == "true"

    if debug:
        logger.info("Enabling verbose logging.")

    standard_handler: "StreamHandler" = StreamHandler(sys.stdout)
    error_handler: "StreamHandler" = StreamHandler(sys.stderr)

    standard_handler.addFilter(lambda record: record.levelno < ERROR)  # keep errors to stderr
    error_handler.setLevel(ERROR)

    basicConfig(
        format="%(asctime)s\t%(levelname)s\t%(name)s@%(threadName)s: %(message)s",
        level=DEBUG if debug else INFO,
        handlers=[standard_handler, error_handler]
    )

    dislog_url: str = args.discord_webhook or environ.get("FREEBOOTER_DISCORD_WEBHOOK", None)

    if dislog_url is not None:
        logger.info("Discord Webhook provided, enabling Discord logging.")

        handler: "DiscordWebhookHandler" = DiscordWebhookHandler(
            dislog_url,
            level=INFO,  # debug is just too much for discord to handle
        )
        rootLogger.addHandler(handler)

    # variables

    in_channels: list[str] = args.in_channels or environ.get("FREEBOOTER_IN_CHANNELS", "").split(",")
    out_channels: list[str] = args.out_channels or environ.get("FREEBOOTER_OUT_CHANNELS", "").split(",")

    if len(in_channels) < 1:
        logger.fatal("No input channels were provided.")
        return
    else:
        logger.info(f"{len(in_channels)} input channel(s) were provided.")

    if len(out_channels) < 1:
        logger.fatal("No output channels were provided.")
        return
    else:
        logger.info(f"{len(out_channels)} output channel(s) were provided.")

    # setup folders

    scratch_folder: "Path" = Path(args.scratch or environ.get("FREEBOOTER_SCRATCH", "scratch"))

    if not scratch_folder.is_absolute():
        scratch_folder = scratch_folder.absolute()

    if not scratch_folder.exists():
        scratch_folder.mkdir(parents=True)
        logger.debug(f"Created scratch folder in {scratch_folder}")

    config_folder: "Path" = Path(args.config or environ.get("FREEBOOTER_CONFIG", "config"))

    if not config_folder.is_absolute():
        config_folder = config_folder.absolute()

    if not config_folder.exists():
        config_folder.mkdir(parents=True)
        logger.debug(f"Created config folder in {config_folder}")

    file_manager: "FileManager" = FileManager(scratch_folder)

    # Check the config folder for valid files

    logger.info("Checking validity of config files...")

    client_secret_schema_path: "Traversable" = ASSETS / "client-secret-schema.json"

    with client_secret_schema_path.open() as schema_fp:
        client_secret_schema: dict = json.load(schema_fp)

    oauth2_token_schema_path: "Traversable" = ASSETS / "oauth2-token-schema.json"

    with oauth2_token_schema_path.open() as schema_fp:
        oauth2_token_schema: dict = json.load(schema_fp)

    for config_file in config_folder.iterdir():
        if config_file.is_file() and config_file.suffix == ".json":
            with config_file.open() as cs_fp:
                client_secret_data: dict = json.load(cs_fp)

            if config_file.stem.endswith("-oauth2"):
                schema = oauth2_token_schema
            else:
                schema = client_secret_schema

            validate(instance=client_secret_data, schema=schema)
            logger.debug(f"Validated {config_file.name} with {schema['title']} JSON schema.")

    logger.info("Done. Config files are valid, proceeding...")

    # OAuth2 authorization (CLI only)

    if args.authorize_oauth2:
        logger.info("Starting OAuth2 authorization flow.")

        for config_file in config_folder.iterdir():
            if config_file.is_file() \
                    and config_file.suffix == ".json" \
                    and not config_file.stem.endswith("-oauth2"):
                logger.info(f"Found client secret file {config_file}, attempting to authorize.")

                client_secret_final_pathnane: str = config_file.stem + "-oauth2" + config_file.suffix
                client_secret_final: "Path" = config_file.parent.joinpath(client_secret_final_pathnane)

                if client_secret_final.exists():
                    logger.info(f"OAuth2 token already exists for {config_file}, skipping.")
                    continue
                else:
                    flow: "Flow" = Flow.from_client_secrets_file(
                        str(config_file),
                        scopes=[YOUTUBE_UPLOAD_SCOPE],
                        redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                    )

                    # Tell the user to go to the authorization URL.
                    auth_url, _ = flow.authorization_url(prompt="consent")

                    logger.info(f"Please check stdout for authorization instructions.")
                    print(f"Please go to this URL: {auth_url}")

                    # The user will get an authorization code. This code is used to get the
                    # access token.
                    code: str = input('Enter the authorization code: ')
                    token: "OAuth2Token" = flow.fetch_token(code=code)

                    logger.info(f"Successfully authorized {config_file}.")

                    # Save the credentials for productionr uns
                    with client_secret_final.open("w") as fp:
                        json.dump(token, fp)

                    logger.info(f"Saved OAuth2 token to {client_secret_final}.")
            else:
                continue
        return
    else:
        logger.debug("Skipping OAuth2 authorization flow.")

    # MariaDB configuration

    db_host: str = args.db_host or environ.get("FREEBOOTER_MYSQL_HOST", "localhost")
    db_port: int = args.db_port or int(environ.get("FREEBOOTER_MYSQL_PORT", "3306"))
    db_database: str = args.db_database or environ.get("FREEBOOTER_MYSQL_DATABASE", "freebooter")
    db_user: str = args.db_user or environ.get("FREEBOOTER_MYSQL_USER", "freebooter")
    db_password: str = args.db_password or environ.get("FREEBOOTER_MYSQL_PASSWORD", "freebooter")

    logger.info("Initializing MariaDB connection pool...")

    pool: "ConnectionPool" = ConnectionPool(
        host=db_host,
        port=db_port,
        database=db_database,
        user=db_user,
        password=db_password,
        pool_name="freebooter",
    )

    logger.info("MariaDB connection OK.")

    logger.info("Done.")

    # Setup Uploaders

    uploaders: list["Uploader"] = []

    logger.info("Setting up uploaders...")

    for channel in out_channels:
        uploader: "Uploader"
        platform: "Platform" = Platform.find_from_out_channel(channel)
        match platform:
            case Platform.YOUTUBE:
                assert youtube_api_key is not None, "YouTube API key is required for YouTube uploads."
                uploader = YouTubeUploader.create_from_config_files(config_folder, channel, youtube_api_key)
            # future platforms will go here
        uploaders.append(uploader)

    # Take downloaded videos and upload them

    upload_thread_pool: "ThreadPoolExecutor" = ThreadPoolExecutor(
        thread_name_prefix="Uploader-",
        max_workers=len(uploaders)  # arbitrary, but somewhat reasonable since each uploader implements a lock
    )

    def upload_handler(scratch: "ScratchFile", metadata: "MediaMetadata") -> "list[MediaMetadata]":
        # Can't be an anoymous function
        # See https://stackoverflow.com/questions/1233448/no-multiline-lambda-in-python-why-not
        uploaded_vidoes: "list[MediaMetadata]" = []

        upload_futures: "list[Future[MediaMetadata | None]]" = []

        # we use futures and a thread pool so that we can have multiple uploaders running at once for each watcher call

        # what happens if we are at the max workers? it should block until one frees (desired behavior)

        for uploader in uploaders:
            upload_future: "Future[MediaMetadata | None]" = upload_thread_pool.submit(uploader.upload, scratch,
                                                                                      metadata)
            upload_futures.append(upload_future)

        for upload_future in upload_futures:
            uploaded_video: "MediaMetadata | None" = upload_future.result()
            if uploaded_video is not None:
                uploaded_vidoes.append(uploaded_video)

        return uploaded_vidoes

    logger.info("Done.")

    # Setup Watchers

    shutdown_event: "Event" = Event()

    watchers: list["Watcher"] = []

    logger.info("Setting up watchers...")

    for channel in in_channels:
        watcher: "Watcher"
        platform: "Platform" = Platform.find_from_in_channel(channel)
        match platform:
            case Platform.YOUTUBE:
                watcher = YouTubeChannelWatcher(
                    shutdown_event,
                    upload_handler,
                    pool,
                    file_manager,
                    channel_id=channel,
                    copy=args.copy,
                )
            # future platforms will go here
        watchers.append(watcher)

    logger.info("Done.")

    # Run

    logger.info("Starting watchers...")

    for watcher in watchers:
        watcher.start()

    logger.info("Done.")

    # Wait for watchers to finish

    logger.info("Setup complete. Ready!")

    try:
        for watcher in watchers:
            watcher.join()
        exit(1)  # shouldn't be possible
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Stopping watchers...")
        shutdown_event.set()
        for watcher in watchers:
            watcher.join()
        logger.info("Done, closing uploaders...")
        upload_thread_pool.shutdown(wait=True)
        for uploader in uploaders:
            uploader.close()


if __name__ == "__main__":
    main()
