# Dockerfile for sandbox api, allowing for new sandbox dockerfiles to be spun up when needed
# Ubuntu
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/London \
	PATH="/home/subrunner/.local/bin:${PATH}" \
	PYTHONPATH="/home/subrunner:/home/subrunner/runner:${PYTHONPATH}"

# Install from apt-get
RUN apt-get update \
&& apt-get install -y python3.8 python3-pip bash git libpq-dev apt-utils \
&& ln -sf python3 /usr/bin/python

# Install docker
ADD https://get.docker.com/ /tmp/get_docker.sh
RUN chmod +x /tmp/get_docker.sh && /tmp/get_docker.sh

# Add user
RUN useradd subrunner -m -G docker

# Add python requirements as user
USER subrunner
RUN python3 -m pip install --upgrade pip setuptools wheel
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Add scripts
VOLUME ["/tmp/sandbox"]
COPY --chown=subrunner runner /home/subrunner/runner
COPY --chown=subrunner sandbox /home/subrunner/sandbox
COPY --chown=subrunner shared /home/subrunner/shared
ADD --chown=subrunner https://raw.githubusercontent.com/AI-Wars-Soc/common/main/default_config.yml /home/subrunner/default_config.yml

# Set up repositories
RUN mkdir /home/subrunner/repositories
VOLUME /home/subrunner/repositories

# Set user dir
WORKDIR /home/subrunner
CMD [ "bash", "runner/run.sh" ]
