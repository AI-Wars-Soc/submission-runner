# Dockerfile for sandbox api, allowing for now sandbox dockerfiles to be spun up when needed
FROM docker

# Install python
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Add scripts
VOLUME /sandbox-scripts
COPY sandbox-scripts /sandbox-scripts-src
COPY /runner /runner

# Set up permissions for inside sandbox (uid 1429)
RUN chown -R 1429 /sandbox-scripts-src

CMD [ "/runner/run.sh" ]