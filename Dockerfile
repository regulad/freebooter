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

FROM python:3.11-alpine

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  POETRY_HOME=/opt/poetry \
  POETRY_VERSION=1.3.1

# Add dependencies
RUN apk add curl ffmpeg

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Safe working directory
WORKDIR /app

# Copy dependencies
COPY poetry.lock pyproject.toml /app/

# Project initialization:
RUN /opt/poetry/bin/poetry install --without dev --no-interaction --no-ansi

# Creating folders, and files for a project:
COPY . /app

# Startup command:
CMD ["/opt/poetry/bin/poetry", "run", "python", "-m", "freebooter"]
