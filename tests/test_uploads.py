from os import environ
from pathlib import Path

from freebooter import YouTubeUploader, MediaMetadata, Platform, ScratchFile


def test_youtube_uploader() -> None:
    config_folder: "Path" = Path(environ.get("FREEBOOTER_CONFIG", "config"))

    if not config_folder.is_absolute():
        config_folder = config_folder.absolute()

    if not config_folder.exists():
        config_folder.mkdir(parents=True)

    uploader: "YouTubeUploader" = YouTubeUploader.create_from_config_files(
        config_folder,
        environ.get("FREEBOOTER_OUT_CHANNELS", "").split(",")[0],
        environ["FREEBOOTER_YOUTUBE_API_KEY"]
    )

    try:
        testvideo: "Path" = Path.cwd().joinpath("assets").joinpath("testvideo.mp4")

        assert testvideo.exists(), "Test video does not exist."

        metadata: MediaMetadata = MediaMetadata(
            title="Test Video",
            description="This is a test video.",
            tags=["test", "video"],
            categories=["Trailers"],
            platform=Platform.YOUTUBE,
            media_id="Es44QTJmuZ0"
        )

        scratch_file: "ScratchFile" = ScratchFile(testvideo, should_delete=False)

        with scratch_file:
            return_metadata: "MediaMetadata | None" = uploader.upload(scratch_file, metadata)

        assert return_metadata is not None, "Uploader did not return metadata."

        assert return_metadata.title == metadata.title, "Returned metadata title does not match."
        assert return_metadata.description == metadata.description, "Returned metadata description does not match."
        assert return_metadata.tags == metadata.tags, "Returned metadata tags do not match."
        assert len(return_metadata.categories) == 1, "Returned metadata categories is wrong length for YouTube."
        assert return_metadata.categories[0] == metadata.categories[0], "Returned metadata category do not match."
        assert return_metadata.platform == metadata.platform, "Returned metadata platform does not match."
        assert return_metadata.id != metadata.id, "Returned metadata video ID matches original."
    finally:
        uploader.close()
