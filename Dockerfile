# Dockerfile for sandbox api, allowing for new sandbox dockerfiles to be spun up when needed
FROM docker

# Install python
RUN apk add --update --no-cache python3 bash git g++ postgresql-dev cargo gcc python3-dev libffi-dev musl-dev zlib-dev jpeg-dev linux-headers && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools wheel numpy

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Add user
RUN addgroup -S docker && adduser -S --shell /bin/bash subrunner -G docker
WORKDIR /home/subrunner

# Add scripts
VOLUME ["/tmp/sandbox"]
COPY runner ./runner
COPY sandbox ./sandbox
COPY shared ./shared
ENV PYTHONPATH="/home/subrunner:/home/subrunner/runner:${PYTHONPATH}"

# Set up repositories
RUN mkdir /repositories
RUN chown -R subrunner /repositories
RUN chmod u+rw /repositories

# Set user
WORKDIR /home/subrunner/runner
USER subrunner

CMD [ "bash", "run.sh" ]
