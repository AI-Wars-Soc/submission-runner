# Dockerfile for sandbox api, allowing for new sandbox dockerfiles to be spun up when needed
# Ubuntu
FROM ubuntu:20.04

# Add user
RUN groupadd docker \
&& useradd subrunner -m -G docker

# Install from apt-get
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/London \
	PATH="/home/subrunner/.local/bin:${PATH}"
RUN apt-get update \
&& apt-get install -y docker python3 python3-pip bash git libpq-dev \
&& ln -sf python3 /usr/bin/python

# Add python requirements as user
USER subrunner
RUN ls -al /home
RUN python3 -m pip install --upgrade pip setuptools wheel
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt
USER root

# Add scripts
VOLUME ["/tmp/sandbox"]
COPY runner /home/subrunner/runner
COPY sandbox /home/subrunner/sandbox
COPY shared /home/subrunner/shared
ADD --chown=subrunner https://raw.githubusercontent.com/AI-Wars-Soc/common/main/default_config.yml /home/subrunner/default_config.yml
ENV PYTHONPATH="/home/subrunner:/home/subrunner/runner:${PYTHONPATH}"

# Set up repositories
USER subrunner
RUN mkdir /home/subrunner/repositories
VOLUME /home/subrunner/repositories

# Set user dir
WORKDIR /home/subrunner
CMD [ "bash", "runner/run.sh" ]
