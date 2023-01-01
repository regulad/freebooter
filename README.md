# freebooter

[![wakatime](https://wakatime.com/badge/regulad/freebooter/coda-wakatime.svg)](https://wakatime.com)

`freebooter` downloads photos & videos from the internet and uploads it onto your social media accounts.

## NOTICE

Please don't use this project in production, that would be very immoral. This project is for educational purposes only.

`freebooter` is still just a proof-of-concept.

## TODO

This package isn't yet complete. There's still work to be done!

### Platforms

- [ ] TikTok Watching & Uploading Support
- [ ] YouTube Shorts Watching & Uploading (OAuth, not sure if it's possible) Support
- [ ] Instagram Watching & Uploading Support
- [ ] YouTube Uploader Support via Scraping
  - The YouTube Data API only allows uploading private videos. This won't let anybody watch the freebooted videos!\

### Features

- [ ] Proxy Support
- [ ] JSON-Defined Video Filters (Changing with ffmpeg)
- [ ] JSON-Defined Metadata Filters

## Installation

### Local

```bash
git clone https://github.com/regulad/freebooter.git && cd freebooter

# Install dependencies & setup virtual environment
poetry install
```

### Docker

```bash
git clone https://github.com/regulad/freebooter.git && cd freebooter

# See the docker-compose.yml file for more information
docker-compose up -d
```

## Configuration

All configuration is done through either environment variables (handy for Docker deployment) or arguments passed to the CLI (handy for validation).

Run `freebooter -h` to see all available options.

### Environment Variables

* `FREEBOOTER_DEBUG`: Enable verbose logging. `true` or `false`. Defaults to `false`.
* `FREEBOOTER_DISCORD_WEBHOOK`: A Discord webhook URL to send logging messages to. Uses the logging level previously set. Defaults to None.
* `FREEBOOTER_IN_CHANNELS`: A comma-separated list of YouTube channel IDs to download videos from. **Required.**
* `FREEBOOTER_OUT_CHANNELS`: A comma-seperated list of client secret files in the config folder. They must have a refresh token pair made. **Required.**
* `FREEBOOTER_YOUTUBE_API_KEY`: A YouTube Data API key. **Required** to use YouTube Uploaders.
* `FREEBOOTER_SCRATCH`: A directory to store temporary files in. Defaults to `./scratch`.
* `FREEBOOTER_CONFIG`: A directory to store config files in. Defaults to `./config`.
* `FREEBOOTER_MYSQL_HOST`: The MariaDB host to connect to. Defaults to `localhost`.
* `FREEBOOTER_MYSQL_PORT`: The MariaDB port to connect to. Defaults to `3306`.
* `FREEBOOTER_MYSQL_DATABASE`: The MariaDB database to connect to. Defaults to `freebooter`.
* `FREEBOOTER_MYSQL_USER`: The MariaDB user to connect as. Defaults to `freebooter`.
* `FREEBOOTER_MYSQL_PASSWORD`: The MariaDB password to connect with. Defaults to `freebooter`.

### Config Files

The files stored in your config directory are used to store the YouTube Data API client secrets.

See the below format.

```json
{
  "web": {
    "client_id": "[[INSERT CLIENT ID HERE]]",
    "client_secret": "[[INSERT CLIENT SECRET HERE]]",
    "redirect_uris": [],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://accounts.google.com/o/oauth2/token"
  }
}
```

Note that the following scopes are required on your OAuth2 consent page:

* `https://www.googleapis.com/auth/youtube.upload`

You can use these configs to generate a refresh token & access token.

```bash
freebooter -a
```

After this, you can use the config folder.

### Example `./config/` Directory

```bash
./config
├── client_secret_520018178427-44dirukjfm5qvp7velt5trhv9ocja8ge.apps.googleusercontent.com.json
└── client_secret_520018178427-44dirukjfm5qvp7velt5trhv9ocja8ge.apps.googleusercontent.com-oauth2.json
```

The files must start with `client_secret` and end with `.json` to be parsed and processed correctly.

The `OUT_CHANNEL` for this set would be `client_secret_520018178427-44dirukjfm5qvp7velt5trhv9ocja8ge.apps.googleusercontent.com`.

The CLI will automatically append `.json` and `-oauth2` to the end of the config file name.
