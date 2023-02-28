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

import time
from threading import Lock
from typing import Any, Generator, ClassVar

import ffmpeg
from PIL import Image
from tweepy import OAuth1UserHandler, API
from tweepy.models import Media, Status

from .common import Uploader
from ..file_management import ScratchFile
from ..metadata import MediaMetadata, MediaType
from ..middlewares import Middleware

MAC_OAUTH_CONSUMER_KEY = "3rJOl1ODzm9yZy63FACdg"
MAC_OAUTH_CONSUMER_SECRET = "5jPoQ5kQvMJFDYRNE8bQ4rHuds4xJqhvgNJM4awaE8"


# The following are a set of secrets pulled from another nefarium project (neotw) that went unfisn


class TweepyTwitterUploader(Uploader):
    """
    An uploader that uses the tweepy Python package to upload media to Twitter.
    """

    glock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        name: str,
        preprocessors: list[Middleware],
        *,
        # tweepy config
        consumer_key: str = MAC_OAUTH_CONSUMER_KEY,
        consumer_secret: str = MAC_OAUTH_CONSUMER_SECRET,
        access_token: str,
        access_token_secret: str,
        tweepy_kwargs: dict[str, Any] | None = None,
        tweepy_upload_kwargs: dict[str, Any] | None = None,
        tweepy_post_kwargs: dict[str, Any] | None = None,
        proxy: str | None = None,
        # uploader config
        medias_per_tweet: int = 1,
        post_if_indivisible: bool = True,
        **config,
    ) -> None:
        super().__init__(name, preprocessors, **config)

        self._tweepy_upload_kwargs: dict[str, Any] = tweepy_upload_kwargs or {}

        self._tweepy_upload_kwargs.setdefault("chunked", True)

        self._tweepy_post_kwargs: dict[str, Any] = tweepy_post_kwargs or {}

        # API
        self._oauth_handler = OAuth1UserHandler(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )

        tweepy_kwargs_nonnone = tweepy_kwargs or {}

        tweepy_kwargs_nonnone.setdefault("proxy", proxy)
        tweepy_kwargs_nonnone.setdefault("retry_count", 3)
        tweepy_kwargs_nonnone.setdefault("retry_delay", 3)
        tweepy_kwargs_nonnone.setdefault("wait_on_rate_limit", True)

        self._api = API(self._oauth_handler)

        self._medias_per_tweet = medias_per_tweet
        self._post_if_indivisible = post_if_indivisible

    def upload_medias_to_twitter(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> Generator[tuple[ScratchFile, MediaMetadata, Media | None], None, None]:
        """
        Uploads the given medias to Twitter.
        :param medias: A list of tuples of (file, metadata) to upload.
        :return: A generator that yields (file, input_metadata, twitter_media) tuples.
        """
        assert self._file_manager is not None, "File manager is None!"

        for media_pair in medias:
            file, metadata = media_pair
            try:
                self.logger.debug(f"Uploading {file.path} to Twitter")

                # Twitter file formats & limits (according to twitter as of 2/20/2023):
                #  - Image 5 MB
                #  - GIF 15 MB
                #  - Video 512 MB (when using media_category=amplify)

                # Formats that did NOT work:
                #  - tiff
                #  - heic

                # Formats that worked:
                #  - mp4
                #  - mkv
                #  - gif
                #  - png
                #  - jpeg

                twitter_media: Media
                # Twitter's officially supported file formats are GIF, PNG, and JPEG.
                # We can upload them raw here.
                if file.path.suffix in [".gif", ".png", ".jpeg"]:
                    twitter_media = self._api.media_upload(str(file.path), **self._tweepy_upload_kwargs)
                # For other photos, we need to convert them to JPG with Pillow, this is pretty trivial.
                elif metadata.type is MediaType.PHOTO:
                    with self._file_manager.get_file(file_extension=".jpg") as jpg_scratch:
                        with Image.open(file.path) as other_image, other_image.convert("RGB") as rgb_image:
                            rgb_image.save(jpg_scratch.path, format="JPEG", quality=95)

                        twitter_media = self._api.media_upload(str(jpg_scratch.path), **self._tweepy_upload_kwargs)
                # Videos are fine too, but we need to use the media_category=tweet_video parameter.
                # Tweepy also has a bug with wait_for_async_finalize=True, so we need to set it to False.
                elif metadata.type is MediaType.VIDEO:
                    with self._file_manager.get_file(file_extension=".mp4") as mp4_scratch:
                        # We need to convert the video to MP4 with ffmpeg.
                        # Even if it is an MP4, we may need to re-encode it to make it support twitter.
                        # We also need to set the video to 720p, as twitter doesn't support higher resolutions
                        (
                            ffmpeg.input(str(file.path.resolve()))
                            .filter("scale", height="720")
                            .output(str(mp4_scratch.path.resolve()))
                            .run()
                        )

                        # Send it!!
                        kwargs_copy = self._tweepy_upload_kwargs.copy()
                        kwargs_copy["wait_for_async_finalize"] = False
                        # This is broken in tweepy. It generates a KeyError if wait_for_async_finalize is not set to
                        # False.
                        twitter_media = self._api.media_upload(
                            str(mp4_scratch.path),
                            media_category="tweet_video",
                            **kwargs_copy,
                        )
                        time.sleep(20)  # probably how long it takes?
                        # since the wait_for_async_finalize is broken, we need to wait for the video to upload
                # If it isn't a photo or video, what do we do with it?: we raise an error.
                else:
                    raise ValueError(f"Unknown media type: {metadata.type}")

                self.logger.debug(f"Uploaded {file.path} to Twitter with media ID {twitter_media.media_id_string}.")

                yield file, metadata, twitter_media
            except Exception as e:
                self.logger.exception(f"Error uploading media to Twitter: {e}", exc_info=e)
                yield file, metadata, None

    def post_with_twitter_medias(self, metadata: MediaMetadata, twitter_medias: list[Media]) -> MediaMetadata:
        """
        Posts the given medias to Twitter and returns a new MediaMetadata from the status that was posted.
        """
        kwargs = self._tweepy_post_kwargs.copy()

        kwargs.setdefault("status", metadata.title)
        kwargs["media_ids"] = [twitter_media.media_id for twitter_media in twitter_medias]  # type: ignore

        status: Status = self._api.update_status(**kwargs)

        self.logger.info(f"Posted status to Twitter: {status.text} with {len(twitter_medias)} medias.")

        # This class is barely documented, so I included this below for future reference.

        # Status(_api=<tweepy.api.API object at 0x10685d310>, _json={'created_at': 'Tue Feb 21 14:29:45 +0000 2023',
        # 'id': 1628039276972605440, 'id_str': '1628039276972605440', 'text': 'Image_20230217_095846_162
        # https://t.co/uD7ughdeVS', 'truncated': False, 'entities': {'hashtags': [], 'symbols': [], 'user_mentions':
        # [], 'urls': [], 'media': [{'id': 1628039239098040321, 'id_str': '1628039239098040321', 'indices': [26, 49],
        # 'media_url': 'http://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 650, 'height': 434, 'focus_rects': [{'x': 0, 'y': 70, 'h': 364, 'w': 650}, {'x': 0, 'y': 0,
        # 'h': 434, 'w': 434}, {'x': 0, 'y': 0, 'h': 434, 'w': 381}, {'x': 38, 'y': 0, 'h': 434, 'w': 217}, {'x': 0,
        # 'y': 0, 'h': 434, 'w': 650}]}, 'sizes': {'thumb': {'w': 150, 'h': 150, 'resize': 'crop'}, 'small': {'w':
        # 650, 'h': 434, 'resize': 'fit'}, 'medium': {'w': 650, 'h': 434, 'resize': 'fit'}, 'large': {'w': 650,
        # 'h': 434, 'resize': 'fit'}}, 'features': {'small': {'faces': []}, 'medium': {'faces': []},
        # 'orig': {'faces': []}, 'large': {'faces': []}}}]}, 'extended_entities': {'media': [{'id':
        # 1628039239098040321, 'id_str': '1628039239098040321', 'indices': [26, 49], 'media_url':
        # 'http://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 650, 'height': 434, 'focus_rects': [{'x': 0, 'y': 70, 'h': 364, 'w': 650}, {'x': 0, 'y': 0,
        # 'h': 434, 'w': 434}, {'x': 0, 'y': 0, 'h': 434, 'w': 381}, {'x': 38, 'y': 0, 'h': 434, 'w': 217}, {'x': 0,
        # 'y': 0, 'h': 434, 'w': 650}]}, 'sizes': {'thumb': {'w': 150, 'h': 150, 'resize': 'crop'}, 'small': {'w':
        # 650, 'h': 434, 'resize': 'fit'}, 'medium': {'w': 650, 'h': 434, 'resize': 'fit'}, 'large': {'w': 650,
        # 'h': 434, 'resize': 'fit'}}, 'features': {'small': {'faces': []}, 'medium': {'faces': []},
        # 'orig': {'faces': []}, 'large': {'faces': []}}, 'media_key': '3_1628039239098040321'},
        # {'id': 1628039243451842560, 'id_str': '1628039243451842560', 'indices': [26, 49], 'media_url':
        # 'http://pbs.twimg.com/media/Fpf1EPJXwAA5h85.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1EPJXwAA5h85.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 1440, 'height': 960, 'focus_rects': [{'x': 0, 'y': 154, 'h': 806, 'w': 1440}, {'x': 132, 'y': 0,
        # 'h': 960, 'w': 960}, {'x': 191, 'y': 0, 'h': 960, 'w': 842}, {'x': 372, 'y': 0, 'h': 960, 'w': 480},
        # {'x': 0, 'y': 0, 'h': 960, 'w': 1440}]}, 'sizes': {'thumb': {'w': 150, 'h': 150, 'resize': 'crop'},
        # 'small': {'w': 680, 'h': 453, 'resize': 'fit'}, 'medium': {'w': 1200, 'h': 800, 'resize': 'fit'},
        # 'large': {'w': 1440, 'h': 960, 'resize': 'fit'}}, 'features': {}, 'media_key': '3_1628039243451842560'},
        # {'id': 1628039252201046016, 'id_str': '1628039252201046016', 'indices': [26, 49], 'media_url':
        # 'http://pbs.twimg.com/media/Fpf1EvvWAAAGfSm.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1EvvWAAAGfSm.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 3024, 'height': 4032}, 'sizes': {'large': {'w': 1536, 'h': 2048, 'resize': 'fit'}, 'thumb': {'w':
        # 150, 'h': 150, 'resize': 'crop'}, 'medium': {'w': 900, 'h': 1200, 'resize': 'fit'}, 'small': {'w': 510,
        # 'h': 680, 'resize': 'fit'}}, 'features': {}, 'media_key': '3_1628039252201046016'}]}, 'source': '<a
        # href="http://itunes.apple.com/us/app/twitter/id409789998?mt=12" rel="nofollow">Twitter for Mac</a>',
        # 'in_reply_to_status_id': None, 'in_reply_to_status_id_str': None, 'in_reply_to_user_id': None,
        # 'in_reply_to_user_id_str': None, 'in_reply_to_screen_name': None, 'user': {'id': 1517672754950115328,
        # 'id_str': '1517672754950115328', 'name': 'regulad', 'screen_name': 'regulad02', 'location':
        # 'C:\\Users\\parke', 'description': '(previously @regulad01, backup @JensShiggins) 🇺🇸🦅 Runs @andre_frames
        # & working on a Twitter thing DM for info', 'url': 'https://t.co/L5wUzamHx7', 'entities': {'url': {'urls': [
        # {'url': 'https://t.co/L5wUzamHx7', 'expanded_url': 'https://www.regulad.xyz', 'display_url': 'regulad.xyz',
        # 'indices': [0, 23]}]}, 'description': {'urls': []}}, 'protected': False, 'followers_count': 22,
        # 'fast_followers_count': 0, 'normal_followers_count': 22, 'friends_count': 230, 'listed_count': 0,
        # 'created_at': 'Sat Apr 23 01:13:38 +0000 2022', 'favourites_count': 7225, 'utc_offset': None, 'time_zone':
        # None, 'geo_enabled': True, 'verified': False, 'statuses_count': 604, 'media_count': 90, 'lang': None,
        # 'contributors_enabled': False, 'is_translator': False, 'is_translation_enabled': False,
        # 'profile_background_color': 'F5F8FA', 'profile_background_image_url': None,
        # 'profile_background_image_url_https': None, 'profile_background_tile': False, 'profile_image_url':
        # 'http://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg', 'profile_image_url_https':
        # 'https://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg', 'profile_banner_url':
        # 'https://pbs.twimg.com/profile_banners/1517672754950115328/1658858002', 'profile_link_color': '1DA1F2',
        # 'profile_sidebar_border_color': 'C0DEED', 'profile_sidebar_fill_color': 'DDEEF6', 'profile_text_color':
        # '333333', 'profile_use_background_image': True, 'has_extended_profile': True, 'default_profile': True,
        # 'default_profile_image': False, 'pinned_tweet_ids': [1529629155809439744], 'pinned_tweet_ids_str': [
        # '1529629155809439744'], 'has_custom_timelines': True, 'can_media_tag': True, 'followed_by': False,
        # 'following': False, 'follow_request_sent': False, 'notifications': False, 'advertiser_account_type':
        # 'none', 'advertiser_account_service_levels': [], 'analytics_type': 'disabled', 'business_profile_state':
        # 'none', 'translator_type': 'none', 'withheld_in_countries': [], 'require_some_consent': False},
        # 'geo': None, 'coordinates': None, 'place': None, 'contributors': None, 'is_quote_status': False,
        # 'retweet_count': 0, 'favorite_count': 0, 'favorited': False, 'retweeted': False, 'possibly_sensitive':
        # False, 'possibly_sensitive_editable': True, 'lang': 'en', 'supplemental_language': None},
        # created_at=datetime.datetime(2023, 2, 21, 14, 29, 45, tzinfo=datetime.timezone.utc),
        # id=1628039276972605440, id_str='1628039276972605440', text='Image_20230217_095846_162
        # https://t.co/uD7ughdeVS', truncated=False, entities={'hashtags': [], 'symbols': [], 'user_mentions': [],
        # 'urls': [], 'media': [{'id': 1628039239098040321, 'id_str': '1628039239098040321', 'indices': [26, 49],
        # 'media_url': 'http://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 650, 'height': 434, 'focus_rects': [{'x': 0, 'y': 70, 'h': 364, 'w': 650}, {'x': 0, 'y': 0,
        # 'h': 434, 'w': 434}, {'x': 0, 'y': 0, 'h': 434, 'w': 381}, {'x': 38, 'y': 0, 'h': 434, 'w': 217}, {'x': 0,
        # 'y': 0, 'h': 434, 'w': 650}]}, 'sizes': {'thumb': {'w': 150, 'h': 150, 'resize': 'crop'}, 'small': {'w':
        # 650, 'h': 434, 'resize': 'fit'}, 'medium': {'w': 650, 'h': 434, 'resize': 'fit'}, 'large': {'w': 650,
        # 'h': 434, 'resize': 'fit'}}, 'features': {'small': {'faces': []}, 'medium': {'faces': []},
        # 'orig': {'faces': []}, 'large': {'faces': []}}}]}, extended_entities={'media': [{'id': 1628039239098040321,
        # 'id_str': '1628039239098040321', 'indices': [26, 49], 'media_url':
        # 'http://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1D-7WAAEPaVy.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 650, 'height': 434, 'focus_rects': [{'x': 0, 'y': 70, 'h': 364, 'w': 650}, {'x': 0, 'y': 0,
        # 'h': 434, 'w': 434}, {'x': 0, 'y': 0, 'h': 434, 'w': 381}, {'x': 38, 'y': 0, 'h': 434, 'w': 217}, {'x': 0,
        # 'y': 0, 'h': 434, 'w': 650}]}, 'sizes': {'thumb': {'w': 150, 'h': 150, 'resize': 'crop'}, 'small': {'w':
        # 650, 'h': 434, 'resize': 'fit'}, 'medium': {'w': 650, 'h': 434, 'resize': 'fit'}, 'large': {'w': 650,
        # 'h': 434, 'resize': 'fit'}}, 'features': {'small': {'faces': []}, 'medium': {'faces': []},
        # 'orig': {'faces': []}, 'large': {'faces': []}}, 'media_key': '3_1628039239098040321'},
        # {'id': 1628039243451842560, 'id_str': '1628039243451842560', 'indices': [26, 49], 'media_url':
        # 'http://pbs.twimg.com/media/Fpf1EPJXwAA5h85.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1EPJXwAA5h85.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 1440, 'height': 960, 'focus_rects': [{'x': 0, 'y': 154, 'h': 806, 'w': 1440}, {'x': 132, 'y': 0,
        # 'h': 960, 'w': 960}, {'x': 191, 'y': 0, 'h': 960, 'w': 842}, {'x': 372, 'y': 0, 'h': 960, 'w': 480},
        # {'x': 0, 'y': 0, 'h': 960, 'w': 1440}]}, 'sizes': {'thumb': {'w': 150, 'h': 150, 'resize': 'crop'},
        # 'small': {'w': 680, 'h': 453, 'resize': 'fit'}, 'medium': {'w': 1200, 'h': 800, 'resize': 'fit'},
        # 'large': {'w': 1440, 'h': 960, 'resize': 'fit'}}, 'features': {}, 'media_key': '3_1628039243451842560'},
        # {'id': 1628039252201046016, 'id_str': '1628039252201046016', 'indices': [26, 49], 'media_url':
        # 'http://pbs.twimg.com/media/Fpf1EvvWAAAGfSm.jpg', 'media_url_https':
        # 'https://pbs.twimg.com/media/Fpf1EvvWAAAGfSm.jpg', 'url': 'https://t.co/uD7ughdeVS', 'display_url':
        # 'pic.twitter.com/uD7ughdeVS', 'expanded_url':
        # 'https://twitter.com/regulad02/status/1628039276972605440/photo/1', 'type': 'photo', 'original_info': {
        # 'width': 3024, 'height': 4032}, 'sizes': {'large': {'w': 1536, 'h': 2048, 'resize': 'fit'}, 'thumb': {'w':
        # 150, 'h': 150, 'resize': 'crop'}, 'medium': {'w': 900, 'h': 1200, 'resize': 'fit'}, 'small': {'w': 510,
        # 'h': 680, 'resize': 'fit'}}, 'features': {}, 'media_key': '3_1628039252201046016'}]}, source='Twitter for
        # Mac', source_url='http://itunes.apple.com/us/app/twitter/id409789998?mt=12', in_reply_to_status_id=None,
        # in_reply_to_status_id_str=None, in_reply_to_user_id=None, in_reply_to_user_id_str=None,
        # in_reply_to_screen_name=None, author=User(_api=<tweepy.api.API object at 0x10685d310>, _json={'id':
        # 1517672754950115328, 'id_str': '1517672754950115328', 'name': 'regulad', 'screen_name': 'regulad02',
        # 'location': 'C:\\Users\\parke', 'description': '(previously @regulad01, backup @JensShiggins) 🇺🇸🦅 Runs
        # @andre_frames & working on a Twitter thing DM for info', 'url': 'https://t.co/L5wUzamHx7', 'entities': {
        # 'url': {'urls': [{'url': 'https://t.co/L5wUzamHx7', 'expanded_url': 'https://www.regulad.xyz',
        # 'display_url': 'regulad.xyz', 'indices': [0, 23]}]}, 'description': {'urls': []}}, 'protected': False,
        # 'followers_count': 22, 'fast_followers_count': 0, 'normal_followers_count': 22, 'friends_count': 230,
        # 'listed_count': 0, 'created_at': 'Sat Apr 23 01:13:38 +0000 2022', 'favourites_count': 7225, 'utc_offset':
        # None, 'time_zone': None, 'geo_enabled': True, 'verified': False, 'statuses_count': 604, 'media_count': 90,
        # 'lang': None, 'contributors_enabled': False, 'is_translator': False, 'is_translation_enabled': False,
        # 'profile_background_color': 'F5F8FA', 'profile_background_image_url': None,
        # 'profile_background_image_url_https': None, 'profile_background_tile': False, 'profile_image_url':
        # 'http://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg', 'profile_image_url_https':
        # 'https://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg', 'profile_banner_url':
        # 'https://pbs.twimg.com/profile_banners/1517672754950115328/1658858002', 'profile_link_color': '1DA1F2',
        # 'profile_sidebar_border_color': 'C0DEED', 'profile_sidebar_fill_color': 'DDEEF6', 'profile_text_color':
        # '333333', 'profile_use_background_image': True, 'has_extended_profile': True, 'default_profile': True,
        # 'default_profile_image': False, 'pinned_tweet_ids': [1529629155809439744], 'pinned_tweet_ids_str': [
        # '1529629155809439744'], 'has_custom_timelines': True, 'can_media_tag': True, 'followed_by': False,
        # 'following': False, 'follow_request_sent': False, 'notifications': False, 'advertiser_account_type':
        # 'none', 'advertiser_account_service_levels': [], 'analytics_type': 'disabled', 'business_profile_state':
        # 'none', 'translator_type': 'none', 'withheld_in_countries': [], 'require_some_consent': False},
        # id=1517672754950115328, id_str='1517672754950115328', name='regulad', screen_name='regulad02',
        # location='C:\\Users\\parke', description='(previously @regulad01, backup @JensShiggins) 🇺🇸🦅 Runs
        # @andre_frames & working on a Twitter thing DM for info', url='https://t.co/L5wUzamHx7', entities={'url': {
        # 'urls': [{'url': 'https://t.co/L5wUzamHx7', 'expanded_url': 'https://www.regulad.xyz', 'display_url':
        # 'regulad.xyz', 'indices': [0, 23]}]}, 'description': {'urls': []}}, protected=False, followers_count=22,
        # fast_followers_count=0, normal_followers_count=22, friends_count=230, listed_count=0,
        # created_at=datetime.datetime(2022, 4, 23, 1, 13, 38, tzinfo=datetime.timezone.utc), favourites_count=7225,
        # utc_offset=None, time_zone=None, geo_enabled=True, verified=False, statuses_count=604, media_count=90,
        # lang=None, contributors_enabled=False, is_translator=False, is_translation_enabled=False,
        # profile_background_color='F5F8FA', profile_background_image_url=None,
        # profile_background_image_url_https=None, profile_background_tile=False,
        # profile_image_url='http://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg',
        # profile_image_url_https='https://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg',
        # profile_banner_url='https://pbs.twimg.com/profile_banners/1517672754950115328/1658858002',
        # profile_link_color='1DA1F2', profile_sidebar_border_color='C0DEED', profile_sidebar_fill_color='DDEEF6',
        # profile_text_color='333333', profile_use_background_image=True, has_extended_profile=True,
        # default_profile=True, default_profile_image=False, pinned_tweet_ids=[1529629155809439744],
        # pinned_tweet_ids_str=['1529629155809439744'], has_custom_timelines=True, can_media_tag=True,
        # followed_by=False, following=False, follow_request_sent=False, notifications=False,
        # advertiser_account_type='none', advertiser_account_service_levels=[], analytics_type='disabled',
        # business_profile_state='none', translator_type='none', withheld_in_countries=[],
        # require_some_consent=False), user=User(_api=<tweepy.api.API object at 0x10685d310>, _json={'id':
        # 1517672754950115328, 'id_str': '1517672754950115328', 'name': 'regulad', 'screen_name': 'regulad02',
        # 'location': 'C:\\Users\\parke', 'description': '(previously @regulad01, backup @JensShiggins) 🇺🇸🦅 Runs
        # @andre_frames & working on a Twitter thing DM for info', 'url': 'https://t.co/L5wUzamHx7', 'entities': {
        # 'url': {'urls': [{'url': 'https://t.co/L5wUzamHx7', 'expanded_url': 'https://www.regulad.xyz',
        # 'display_url': 'regulad.xyz', 'indices': [0, 23]}]}, 'description': {'urls': []}}, 'protected': False,
        # 'followers_count': 22, 'fast_followers_count': 0, 'normal_followers_count': 22, 'friends_count': 230,
        # 'listed_count': 0, 'created_at': 'Sat Apr 23 01:13:38 +0000 2022', 'favourites_count': 7225, 'utc_offset':
        # None, 'time_zone': None, 'geo_enabled': True, 'verified': False, 'statuses_count': 604, 'media_count': 90,
        # 'lang': None, 'contributors_enabled': False, 'is_translator': False, 'is_translation_enabled': False,
        # 'profile_background_color': 'F5F8FA', 'profile_background_image_url': None,
        # 'profile_background_image_url_https': None, 'profile_background_tile': False, 'profile_image_url':
        # 'http://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg', 'profile_image_url_https':
        # 'https://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg', 'profile_banner_url':
        # 'https://pbs.twimg.com/profile_banners/1517672754950115328/1658858002', 'profile_link_color': '1DA1F2',
        # 'profile_sidebar_border_color': 'C0DEED', 'profile_sidebar_fill_color': 'DDEEF6', 'profile_text_color':
        # '333333', 'profile_use_background_image': True, 'has_extended_profile': True, 'default_profile': True,
        # 'default_profile_image': False, 'pinned_tweet_ids': [1529629155809439744], 'pinned_tweet_ids_str': [
        # '1529629155809439744'], 'has_custom_timelines': True, 'can_media_tag': True, 'followed_by': False,
        # 'following': False, 'follow_request_sent': False, 'notifications': False, 'advertiser_account_type':
        # 'none', 'advertiser_account_service_levels': [], 'analytics_type': 'disabled', 'business_profile_state':
        # 'none', 'translator_type': 'none', 'withheld_in_countries': [], 'require_some_consent': False},
        # id=1517672754950115328, id_str='1517672754950115328', name='regulad', screen_name='regulad02',
        # location='C:\\Users\\parke', description='(previously @regulad01, backup @JensShiggins) 🇺🇸🦅 Runs
        # @andre_frames & working on a Twitter thing DM for info', url='https://t.co/L5wUzamHx7', entities={'url': {
        # 'urls': [{'url': 'https://t.co/L5wUzamHx7', 'expanded_url': 'https://www.regulad.xyz', 'display_url':
        # 'regulad.xyz', 'indices': [0, 23]}]}, 'description': {'urls': []}}, protected=False, followers_count=22,
        # fast_followers_count=0, normal_followers_count=22, friends_count=230, listed_count=0,
        # created_at=datetime.datetime(2022, 4, 23, 1, 13, 38, tzinfo=datetime.timezone.utc), favourites_count=7225,
        # utc_offset=None, time_zone=None, geo_enabled=True, verified=False, statuses_count=604, media_count=90,
        # lang=None, contributors_enabled=False, is_translator=False, is_translation_enabled=False,
        # profile_background_color='F5F8FA', profile_background_image_url=None,
        # profile_background_image_url_https=None, profile_background_tile=False,
        # profile_image_url='http://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg',
        # profile_image_url_https='https://pbs.twimg.com/profile_images/1517673160082173952/FqMyjmOj_normal.jpg',
        # profile_banner_url='https://pbs.twimg.com/profile_banners/1517672754950115328/1658858002',
        # profile_link_color='1DA1F2', profile_sidebar_border_color='C0DEED', profile_sidebar_fill_color='DDEEF6',
        # profile_text_color='333333', profile_use_background_image=True, has_extended_profile=True,
        # default_profile=True, default_profile_image=False, pinned_tweet_ids=[1529629155809439744],
        # pinned_tweet_ids_str=['1529629155809439744'], has_custom_timelines=True, can_media_tag=True,
        # followed_by=False, following=False, follow_request_sent=False, notifications=False,
        # advertiser_account_type='none', advertiser_account_service_levels=[], analytics_type='disabled',
        # business_profile_state='none', translator_type='none', withheld_in_countries=[],
        # require_some_consent=False), geo=None, coordinates=None, place=None, contributors=None,
        # is_quote_status=False, retweet_count=0, favorite_count=0, favorited=False, retweeted=False,
        # possibly_sensitive=False, possibly_sensitive_editable=True, lang='en', supplemental_language=None)

        ret_metadata = MediaMetadata.from_tweepy_status_model(status)

        return ret_metadata

    def twitter_post_generator(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> Generator[tuple[ScratchFile, MediaMetadata | None], None, None]:
        """
        Uploads the given medias to Twitter and posts them in batches of self._medias_per_tweet.
        """
        last_x_medias: list[tuple[ScratchFile, MediaMetadata, Media | None]] = []
        for media in self.upload_medias_to_twitter(medias):
            file, metadata, twitter_media = media
            # Did the upload complete?
            if twitter_media is not None:
                # Do we have enough medias accumulated to post?
                last_x_medias.append(media)
                # If we don't, just move along.
                if len(last_x_medias) < self._medias_per_tweet:
                    continue
                # If we do, let's upload them!
                # We always increment one at a time, so we don't need to check > or == for the limit, == will do.
                elif len(last_x_medias) == self._medias_per_tweet or len(last_x_medias) == 4:
                    try:
                        twitter_medias = [twitter_media for _, _, twitter_media in last_x_medias]
                        # The metadata we are about to post with is the most recent.
                        ret_metadata = self.post_with_twitter_medias(metadata, twitter_medias)
                        for file, _, _ in last_x_medias:
                            yield file, ret_metadata
                    except Exception as e:
                        self.logger.exception(f"Error posting to Twitter: {e}", exc_info=e)
                        for file, _, _ in last_x_medias:
                            yield file, None
                    finally:
                        # Go around again.
                        last_x_medias.clear()
            # We can't go any further with this file since it failed to upload to twitter.
            else:
                yield file, None
        # Do we have any leftover medias to post, and should we post them?
        if len(last_x_medias) > 0 and self._post_if_indivisible:
            metadata = last_x_medias[-1][1]
            try:
                twitter_medias = [twitter_media for _, _, twitter_media in last_x_medias]
                ret_metadata = self.post_with_twitter_medias(metadata, twitter_medias)
                for file, _, _ in last_x_medias:
                    yield file, ret_metadata
            except Exception as e:
                self.logger.exception(f"Error posting to Twitter: {e}", exc_info=e)
                for file, _, _ in last_x_medias:
                    yield file, None
        # Make sure that they don't go unhandled!
        elif len(last_x_medias) > 0:
            for file, _, _ in last_x_medias:
                yield file, None

    def upload(
        self, medias: list[tuple[ScratchFile, MediaMetadata]]
    ) -> list[tuple[ScratchFile, MediaMetadata | None]]:
        # I like writing generators, but I don't like using them in other parts of the asynchronous code, so this is a
        # bridge.
        return list(self.twitter_post_generator(medias))


__all__ = (
    "TweepyTwitterUploader",
    "MAC_OAUTH_CONSUMER_SECRET",
    "MAC_OAUTH_CONSUMER_KEY",
)
