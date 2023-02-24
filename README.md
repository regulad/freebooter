# freebooter

[![GitHub Repo stars](https://img.shields.io/github/stars/nefarium/freebooter?style=social)](https://github.com/nefarium/freebooter)

[![wakatime](https://wakatime.com/badge/github/regulad/freebooter.svg)](https://wakatime.com/badge/github/regulad/freebooter)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/nefarium/freebooter/docker-publish.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/nefarium/freebooter/master.svg)](https://results.pre-commit.ci/latest/github/nefarium/freebooter/master)
![Lines of code](https://img.shields.io/tokei/lines/github/nefarium/freebooter)

`freebooter` downloads photos & videos from the internet and uploads it onto your social media accounts, automating the
chore of finding posts and taking time to upload them onto your pages.

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

* `FREEBOOTER_DISCORD_WEBHOOK`: A Discord webhook URL to send logging messages to. Uses the logging level previously
  set. Defaults to None.
* `FREEBOOTER_DISCORD_WEBHOOK_MESSAGE`: What message to send on Discord webhook when an error occurs. Defaults to None.
* `FREEBOOTER_SCRATCH`: A directory to store temporary files in. Defaults to `./scratch`.
* `FREEBOOTER_CONFIG`: A directory to store config files in. Defaults to `./config`.
* `FREEBOOTER_CONFIG_FILE`: A YML file to store config in. Defaults to `./config/config.yml`.
* `FREEBOOTER_MYSQL_HOST`: The MariaDB host to connect to. Defaults to `localhost`.
* `FREEBOOTER_MYSQL_PORT`: The MariaDB port to connect to. Defaults to `3306`.
* `FREEBOOTER_MYSQL_DATABASE`: The MariaDB database to connect to. Defaults to `freebooter`.
* `FREEBOOTER_MYSQL_USER`: The MariaDB user to connect as. Defaults to `freebooter`.
* `FREEBOOTER_MYSQL_PASSWORD`: The MariaDB password to connect with. Defaults to `password`.

#### Special Environment Variables

These variables are for global properties of individual watchers, uploaders, and preprocessors.

* `FREEBOOTER_INSTALOADER_USERNAME`: The Instagram username to use for the default Instaloader. Leave it unset to not log in.
* `FREEBOOTER_INSTALOADER_SESSION_FILE`: The Instagram session file to use for the default Instaloader. Leave it unset to let instaloader figure it out. Create it with `instaloader -l`.

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
      tags: [ ]
      categories: [ ]
      description: "follow me if its dank or nah 🥶 #memes #dailymemes #funnymemes #funny #humor #dogs #cats #animals #dank #dankmemes #memeaccount #comedy #ifunny #reddit #redditmemes"
watchers:
  - name: "UrbanRescueRanch"
    type: youtube
    preprocessors: [ ]
    config:
      channel_id: "UCv3mh2P-q3UCtR9-2q8B-ZA"  # urban rescue ranch
      copy: True
  - name: "terriblememes"
    type: rss
    preprocessors: [ ]
    config:
      url: "https://www.reddit.com/user/regularperson0001/m/terriblememes.rss?sort=new"
      headers:
        User-Agent: "android:autos.rope.balls:v1.2.3 (by /u/soggyspaun)"
uploaders:
  - name: "Local"
    type: local
    preprocessors: [ ]
    config:
      path: "./output/"
```

#### Middlewares

| Name            | Type                | Description                                                                                                                                                                                                                                                                                                              | Configuration                                                                                                           |
|-----------------|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| Edit Metadata   | `metadata`          | Edits the metadata of the media file.                                                                                                                                                                                                                                                                                    | `platform`, `title`, `description`, `tags` and `categories`. Set them to `null` to have them be dropped from the media. |
| Collector       | `collector`         | Collects media files from a source, only releasing them when enough have been collected.                                                                                                                                                                                                                                 | `count` is the amount of media files to collect before releasing them.                                                  |
| Dropper/Ignorer | `dropper`/`ignorer` | Randomly drops media files. There is no guarantee any media will make it through, or if any media will be dropped. It closes media when dropping it, so consider only using it on watchers as preprossors or as a middleware, and not as a uploader preprocessor. Use the functionally equivalent ignorer for this task. | `chance` is the chance of a media file being dropped, a float from 0 to 1.                                              |

#### Watchers

| Name                                         | Type                   | Description                                                                                                                                                                                                                                                                                           | Configuration                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
|----------------------------------------------|------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| YouTube                                      | `youtube`              | Watches a YouTube channel for new videos.                                                                                                                                                                                                                                                             | * `channel_id` is the YouTube channel ID to watch.<br/> * `playlist` specifies a playlist ID. Set it to `null` or unset to use the default value (either the default or shorts).<br/> * `shorts` should be set to true if you want to download shorts.<br/> * `backtrack` sets if previous videos should be recorded, or only new ones.                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| RSS                                          | `rss`                  | Watches an RSS feed for new items. Contains specializations for websites with non-standard feeds. Websites with extra feed handlers:<br/> * `reddit.com`<br/> The watcher will attempt to extract information with a YoutubeDL downloader if it cannot find a thumbnail or media URL in a feed entry. | * `url` is the URL of the RSS feed.<br/> * `headers` is a dictionary of headers to send with the request. Any changes made to these headers will also trickle down into the YoutubeDL downloader.<br/> * `proxies` is a mapping of proxies to pass to the requests section. Any changes made to these proxies will also trickle down into the YoutubeDL downloader.<br/> * `retry_count` defines the amount of times to retry an HTTP request before giving up.                                                                                                                                                                                                                                                                                                                                        |
| Local                                        | `local`                | Watches a local directory for new files.                                                                                                                                                                                                                                                              | * `path` is the path to the directory to watch.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Pusher                                       | `pusher`               | Pusher periodically pushes empty media files to the flow. Designed as a companion to the collector middleware, which may have more than the count inserted at once and then be overwhelmed by the flow of new media.                                                                                  | * `interval` is the interval in seconds to push empty media files.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Instagram via `instaloader`                  | `instagram`            | Watches an Instagram profile for new posts.                                                                                                                                                                                                                                                           | * `instaloader_kwargs` defines the keyword arguments to instantiate the Instaloader with. See [their documentation](https://instaloader.github.io/as-module.html) for details.<br/> * `proxies` is a requests-style mapping of protocols to proxies.<br/> * `backtrack` behaves identically to its YouTube counterpart.<br/> * `username` & `userid` are two ways of querying for users. Their names are self-explanatory. One or the other must be defined, and `username` is used first. Consider using `userid` as a fallback if the username is changed.<br/> * `use_default_instaloader` specifies if a new instaloader should be created just for this instance, or if it should instead be pooled. Defaults to `true`. Note that if this is not `false`, and custom kwargs set may not be used! |
| Discord via `discord.py` & `discord.py-self` | `discord` & `selfcord` | Asynchronously listen to a Discord channel for new media being posted.                                                                                                                                                                                                                                | * `token` is the client's authorization token.<br/> * `channels` is an array of integers corresponding to discord channel IDs. <br/> * `discord_client_kwargs` is a list of keyword arguments for the Discord client.<br/> * `jishaku_prefix` is a prefix for the Jishaku command. Set it to `null` to disable Jishaku.<br/> * `backtrack` determines if previous messages should be combed through.                                                                                                                                                                                                                                                                                                                                                                                                   |

##### YouTubeDL Parameters

`youtube` & `rss` can take an additional option: `ytdl_params`. It specifies the parameters to pass to `yt-dlp` when
downloading the media file. See the [yt-dlp documentation](https://github.com/yt-dlp/yt-dlp) for more information.

##### Other common options

All watchers can also take the parameter `preprocessors`. It specifies a list of middleware objects to run on the media
file before passing them into the rest of the flow.
Many watchers also support the parameter `copy`, which will copy data into downloaders even if it has already been
handled before and marked as such.

#### Uploaders

| Name                         | Type        | Description                                                                                                                                                                                                                                                                                                                          | Configuration                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
|------------------------------|-------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Local                        | `local`     | Uploads to a local directory.                                                                                                                                                                                                                                                                                                        | * `path` is the path to the directory to upload to.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Instagram via `instagrapi`   | `instagram` | Uploads to Instagram via the `instagrapi` library.                                                                                                                                                                                                                                                                                   | * `username` is the username to log in as.<br/> * `password` is the password to log in with.<br/> * `otp` is the Base32-encoded time-OTP 2FA secret that can be used to generate 2FA/OTP codes. In most cases, this is not required to have an account that does not get suspended easily. Use with caution when specifying the `delay` arguments, as it may cause the code to expire before Instagram receives the request.<br/> * `proxy` is the proxy to use. (strongly reccomended)<br/> * `retry_count` defines the amount of times to retry an HTTP request before giving up.<br/> * `insta_settings` & `insta_kwargs` are two optional arguments that accept a mapping. They pass the respective settings & keyword arguments into instagrapi. See [the instagrapi documentation](https://adw0rd.github.io/instagrapi/) for more details.<br/> * `session_json_path` should be set to a file that can be written/read to for storing data. No database :(.<br/> * `delay_start` and `delay_end` define the range of time i.e. 1-10 seconds that will be spent before firing each request. Higher values and those with larger variation may cause accounts to be more reliable. If not specified, no time will be sent between sending requests.<br/> * `mode` specifies how videos should be uploaded. Set to `singleton` to make posts with a single photo, `reels` to upload single videos to Instagram Reels, `album` to post albums of photos, `story` to upload to your story, and `igtv` to upload to your IGTV. `hybrid` combines singleton & reels. |
| YouTube via YouTube Data API | `youtube`   | Uploads to YouTube via the YouTube Data API. This API is extremely restrictive and does not allow the reliable upload of shorts nor does it allow posted videos to be public. Consider it "depreciated", however this uploader will remain in freebooter for those that have verified Google API apps that are capable of uploading. | * `youtube_api_key` is the YouTube Data API key (sometimes referred to as a developer key) for your Google Cloud Platform account. This is required to make some requests to the API involving data and categories.<br/> * `client_secret_data` is your OAuth secret data from Google. The filename of the JSON file you download should resemble something like `client_secret_520018178247-44dirukjfm5qpv7velt5trhv9ocja8ge.apps.googleusercontent.com.json`.<br/> * `oauth2_token_data` is your actual OAuth2 token, it can be generated with the included script `freebooter_youtube` along with your client secret/key.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Twitter via `tweepy`         | `twitter`   | Uploads to a Twitter account using the `tweepy` Python library.                                                                                                                                                                                                                                                                      | * `consumer_key` and `consumer_secret` specify the Twitter API consumer key & secret to use when authenticating with Twitter. If omitted, the Twitter for Mac keys will be used.<br/> * `access_token` and `access_token_secret` specify the access token & access token secret to use when authenticating with Twitter. A CLI utility named `freebooter_twitter` is provided for ease of setup, call it with `freebooter_twitter --help` to see all available options.<br/> * `tweepy_kwargs`, `tweepy_upload_kwargs`, and `tweepy_post_kwargs` are additional keyword arguments to pass into `tweepy` during processing. The names are self-explanatory, with the one without a word being used during initialization. See [their documentation](https://docs.tweepy.org/en/stable/) for more info.<br/> * `proxy` is a shortcut to initialize `tweepy` with a proxy. Since we use Twitter's Official API as it has very few limits (at the moment), you probably don't need one.<br/> * `medias_per_tweet` specifies how many different pieces of media should be included in a post. Defaults to one, maximum is four.<br/> * `post_if_indivisible` specifies if the remaining medias after dividing by the `medias_per_tweet` value. Default is True.                                                                                                                                                                                                                                                                                                          |
| Discord via `discord.py`     | `discord`   | Uploads to a Discord webhook.                                                                                                                                                                                                                                                                                                        | * `webhook` is the URL of the webhook to upload to.<br/> * `bot_token` is a bot token to authenticate with. This typically has a higher rate limit. Optional, can be omitted.<br/> * `proxies` is a requests-style proxy field.<br/> * `retry_count` is the amount of times to retry if a connection fails.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

##### Common options

All uploaders can also take the parameter `preprocessors`. It specifies a list of middleware objects to run on the media
file before uploading them.

For big keys like `youtube`'s `client_secret_data` and `oauth2_token_data`, you can use the special
flag `!include xx.json` or `!include xx.yaml` to include the contents of the file `xx.json` or `xx.yaml` in the
configuration file. This is useful for keeping your secrets out of your configuration file, or allowing it to be
readable while you have a lot of files.
