# freebooter

[![wakatime](https://wakatime.com/badge/github/regulad/freebooter.svg)](https://wakatime.com/badge/github/regulad/freebooter)

`freebooter` downloads photos & videos from the internet and uploads it onto your social media accounts.

## NOTICE

Please don't use this project in production, that would be very immoral. This project is for educational purposes only.

`freebooter` is still just a proof-of-concept.

## Installation

### Local

```bash
git clone https://github.com/regulad/freebooter.git && cd freebooter

# Install dependencies & setup virtual environment
poetry install
```

#### Additional Dependencies

* `ffmpeg` (for video processing)
* `mariadb` client libraries (for database)
* `https://phantomjs.org/download.html` (for headless browser used by yt-dlp)

### Docker

```bash
git clone https://github.com/regulad/freebooter.git && cd freebooter

# See the docker-compose.yml file for more information
docker-compose up -d
```

## Configuration

All configuration is done through environment variables (handy for Docker deployment).

### Environment Variables

* `FREEBOOTER_DISCORD_WEBHOOK`: A Discord webhook URL to send logging messages to. Uses the logging level previously set. Defaults to None.
* `FREEBOOTER_DISCORD_WEBHOOK_MESSAGE`: What message to send on Discord webhook when an error occurs. Defaults to None.
* `FREEBOOTER_SCRATCH`: A directory to store temporary files in. Defaults to `./scratch`.
* `FREEBOOTER_CONFIG`: A directory to store config files in. Defaults to `./config`.
* `FREEBOOTER_CONFIG_FILE`: A YML file to store config in. Defaults to `./config/config.yml`.
* `FREEBOOTER_MYSQL_HOST`: The MariaDB host to connect to. Defaults to `localhost`.
* `FREEBOOTER_MYSQL_PORT`: The MariaDB port to connect to. Defaults to `3306`.
* `FREEBOOTER_MYSQL_DATABASE`: The MariaDB database to connect to. Defaults to `freebooter`.
* `FREEBOOTER_MYSQL_USER`: The MariaDB user to connect as. Defaults to `freebooter`.
* `FREEBOOTER_MYSQL_PASSWORD`: The MariaDB password to connect with. Defaults to `password`.

### Config Files

#### `./config/config.yml`

See the JSON schema at `./src/freebooter/assets/config-schema.json` for a definition of the config file.

##### Example

```yaml
middlewares:
  - name: "Edit Metadata"
    type: metadata
    config:
      title: null
      tags: []
      categories: []
      description: "follow me if its dank or nah 🥶 #memes #dailymemes #funnymemes #funny #humor #dogs #cats #animals #dank #dankmemes #memeaccount #comedy #ifunny #reddit #redditmemes"
watchers:
  - name: "UrbanRescueRanch"
    type: youtube
    preprocessors: []
    config:
      channel_id: "UCv3mh2P-q3UCtR9-2q8B-ZA"  # urban rescue ranch
      copy: True
  - name: "terriblememes"
    type: rss
    preprocessors: []
    config:
      url: "https://www.reddit.com/user/regularperson0001/m/terriblememes.rss?sort=new"
      headers:
        User-Agent: "android:autos.rope.balls:v1.2.3 (by /u/soggyspaun)"
uploaders:
  - name: "Local"
    type: local
    preprocessors: []
    config:
      path: "./output/"
  - name: "FreebooterOutTest"
```
