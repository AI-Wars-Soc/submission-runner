# Dockerfile for sandbox api, allowing for now sandbox dockerfiles to be spun up when needed
FROM docker

# Install python
RUN apk add --update --no-cache python3 bash git g++ postgresql-dev cargo gcc python3-dev libffi-dev musl-dev zlib-dev jpeg-dev linux-headers && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools wheel

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Add scripts
VOLUME ["/tmp/sandbox"]
COPY runner /exec/runner
COPY sandbox /exec/sandbox
COPY shared /exec/shared
ENV PYTHONPATH="/exec:${PYTHONPATH}"

# Set up permissions for inside sandbox (uid 1429)
RUN chown -R 1429 /exec/sandbox
RUN chown -R 1429 /exec/shared

# Set up repository permissions
RUN mkdir /repositories
# RUN chown -R 1429 /repositories

CMD [ "bash", "/exec/runner/run.sh" ]
