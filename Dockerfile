#    freebooter downloads photos & videos from the internet and uploads it onto your social media accounts.
#    Copyright (C) 2023 Parker Wahle
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

FROM python:3.11.2-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive \
  PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  POETRY_HOME=/opt/poetry \
  POETRY_VERSION=1.3.1 \
  PYTHONPATH=${PYTHONPATH}:/app/src

# We do the PythonPath thing here instead of installing the package as editable or installing it because it is a little
# bit faster and it is easier to debug.

LABEL maintainer="Parker Wahle <regulad@regulad.xyz>" \
      name="freebooter" \
      version="1.4.2"

# Add curl for MariaDB script
RUN apt update && apt upgrade -y && apt install -y curl

# Add MariaDB apt repositories with script
RUN curl -sSL https://downloads.mariadb.com/MariaDB/mariadb_repo_setup | bash

# Add dependencies
RUN apt update && apt upgrade -y && apt install -y libmariadb3 libmariadb-dev ffmpeg gcc wget fontconfig

# PhantomJS is only used a little by yt-dlp, so we will not install it. If we chose to in the future, it would go here.

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Safe working directory
WORKDIR /app

# Copy dependencies
COPY poetry.lock pyproject.toml /app/

# Project initialization:
RUN /opt/poetry/bin/poetry install --only main --no-interaction --no-ansi --no-root

# Creating folders, and files for a project:
COPY . /app

# Startup command:
CMD ["/opt/poetry/bin/poetry", "run", "python", "-O", "-m", "freebooter"]
