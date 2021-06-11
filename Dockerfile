# Dockerfile for sandbox api, allowing for new sandbox dockerfiles to be spun up when needed
FROM docker

# Add user
RUN addgroup -S docker && adduser -S --shell /bin/bash subrunner -G docker

# Install python
RUN apk add --update --no-cache python3 bash git g++ postgresql-dev cargo gcc python3-dev libffi-dev musl-dev zlib-dev jpeg-dev linux-headers && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools wheel numpy

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Add scripts
VOLUME ["/tmp/sandbox"]
COPY runner /home/subrunner/runner
COPY sandbox /home/subrunner/sandbox
COPY shared /home/subrunner/shared
COPY runner/default_config.yml /home/subrunner/default_config.yml
ENV PYTHONPATH="/home/subrunner:/home/subrunner/runner:${PYTHONPATH}"

# Set up repositories
RUN mkdir /home/subrunner/repositories && chown -R subrunner /home/subrunner
VOLUME /home/subrunner/repositories

# Set user
WORKDIR /home/subrunner
USER subrunner

CMD [ "bash", "runner/run.sh" ]
