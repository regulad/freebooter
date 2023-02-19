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

import typing
from abc import ABCMeta
from shutil import copyfile

import ffmpeg
from ffmpeg.nodes import FilterableStream

from .common import Middleware
from ..file_management import ScratchFile
from ..metadata import MediaMetadata


class FFmpegMiddleware(Middleware, metaclass=ABCMeta):
    """
    Uses ffmpeg to convert media to a format that can be uploaded to various social media platforms.
    This class is currently unused.
    """

    def __init__(self, name: str, *, ffmpeg_options: dict, **config) -> None:
        super().__init__(name, **config)
        self.ffmpeg_options = (
            ffmpeg_options  # todo: this is a placeholder for more advanced logic
        )

    @typing.no_type_check  # ffmpeg doesn't have type annotations
    def process_stream(self, stream: FilterableStream) -> FilterableStream:
        """
        Processes the stream using ffmpeg. Override this method to implement your own logic.
        """
        raise NotImplementedError

    @typing.no_type_check  # ffmpeg doesn't have type annotations
    def _process(
        self, file: ScratchFile, metadata: MediaMetadata
    ) -> tuple[ScratchFile, MediaMetadata] | None:
        assert self.ready, "Middleware is not ready to process files"
        assert (
            self._file_manager is not None
        ), "Middleware is not ready to process files"

        with self._file_manager.get_file(
            file_extension=file.path.suffix
        ) as ffmpeg_scratch:
            # there are two options for doing this with ffmpeg:
            #  1. feeding into stdin and reading from stdout and then overwriting the scratchfile
            #  2. doing a dance with a temporary file
            # I chose the second option because it's easier to implement and I don't think it's
            # going to be a performance bottleneck, plus the first option could take up a lot of memory

            stream: ffmpeg.nodes.FilterableStream = ffmpeg.input(file.path)

            stream = self.process_stream(stream)

            stream = stream.output(ffmpeg_scratch.path)

            stream.run()

            copyfile(ffmpeg_scratch.path, file.path)

            return file, metadata

            # ffmpeg_scratch.path.unlink() is called by the file manager at this point


__all__ = ("FFmpegMiddleware",)
