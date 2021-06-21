# Dockerfile for sandbox api, allowing for new sandbox dockerfiles to be spun up when needed
# Alpine
FROM docker

# Add user
RUN addgroup -S docker \
&& adduser --disabled-password --shell /bin/bash subrunner subrunner \
&& addgroup subrunner docker

# Install python
RUN apk --update upgrade \
&& apk add --update python3 bash git g++ postgresql-dev cargo gcc python3-dev libffi-dev musl-dev zlib-dev jpeg-dev linux-headers make \
&& ln -sf python3 /usr/bin/python

# Add python requirements as user
USER subrunner
RUN python3 -m ensurepip \
&& python3 -m pip install --upgrade pip setuptools wheel numpy gevent
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt
USER root

# Add scripts
VOLUME ["/tmp/sandbox"]
COPY runner /home/subrunner/runner
COPY sandbox /home/subrunner/sandbox
COPY shared /home/subrunner/shared
COPY runner/default_config.yml /home/subrunner/default_config.yml
ENV PYTHONPATH="/home/subrunner:/home/subrunner/runner:${PYTHONPATH}"

# Set up repositories
USER subrunner
RUN mkdir /home/subrunner/repositories
VOLUME /home/subrunner/repositories

# Set user dir
WORKDIR /home/subrunner
CMD [ "bash", "runner/run.sh" ]
