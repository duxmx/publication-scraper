FROM python:3.12-bookworm AS poetry
# Update to latest Poetry version
ENV POETRY_VERSION="2.1.1"

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /publication-scraper

# Copy all necessary files including deduplication feature
COPY pyproject.toml poetry.lock README.md LICENSE ./
COPY pubscraper /publication-scraper/pubscraper/

# Install dependencies and export requirements.txt
RUN poetry install --no-interaction --no-ansi --no-root && \
    poetry run pip freeze > requirements.txt

RUN ls
RUN poetry build


FROM python:3.12
LABEL maintainer="Joseph Hendrix <jlh7459@my.utexas.edu>"

# Update OS
RUN apt-get update && apt-get install -y \
  vim-tiny \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Configure Python/Pip
ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONFAULTHANDLER=1 \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100

WORKDIR /publication-scraper

COPY --from=poetry /publication-scraper /publication-scraper/requirements.txt ./

RUN pip install -r requirements.txt

COPY --from=poetry /publication-scraper/dist/*.whl ./

RUN pip install *.whl

COPY README.md LICENSE /pubscraper/

CMD [ "pubscraper", "--help" ]
