# Dockerfile for sandbox api, allowing for now sandbox dockerfiles to be spun up when needed
FROM docker

# Install python
RUN apk add --update --no-cache python3 bash && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Add scripts
COPY runner /exec/runner
COPY sandbox /exec/sandbox
COPY shared /exec/shared
ENV PYTHONPATH="/exec:${PYTHONPATH}"

# Set up permissions for inside sandbox (uid 1429)
RUN chown -R 1429 /exec/sandbox
RUN chown -R 1429 /exec/shared

CMD [ "bash", "/exec/runner/run.sh" ]