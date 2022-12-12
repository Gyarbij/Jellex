# Base Image: python:3.8-slim
FROM python:3.11-slim

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Docker Environment Variables
ENV DRYRUN 'True'
ENV DEBUG 'True'
ENV DEBUG_LEVEL 'INFO'
ENV SLEEP_DURATION '3600'
ENV LOGFILE 'log.log'
# User Mapping
ENV USER_MAPPING '{ "User Test": "User Test2" }'
ENV LIBRARY_MAPPING '{ "Shows Test": "TV Shows Test" }'
# Plex Environment Variables
ENV PLEX_BASEURL 'http://localhost:32400'
ENV PLEX_TOKEN ''
ENV PLEX_USERNAME ''
ENV PLEX_PASSWORD ''
ENV PLEX_SERVERNAME ''
# Jellyfin Environment Variables
ENV JELLYFIN_BASEURL 'http://localhost:8096'
ENV JELLYFIN_TOKEN ''
# Blacklist/Whitelist Environment Variabless
ENV BLACKLIST_LIBRARY ''
ENV WHITELIST_LIBRARY ''
ENV BLACKLIST_LIBRARY_TYPE  '' 
ENV WHITELIST_LIBRARY_TYPE  ''
ENV BLACKLIST_USERS  ''
ENV WHITELIST_USERS  ''

# Install pip requirements
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

WORKDIR /app
COPY . /app

# Creates a non-root user with an explicit UID and adds permission to access the /app folder.
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden.
CMD ["python", "src/jellex.py"]
