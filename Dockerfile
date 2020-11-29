# Dockerfile for sandbox api, allowing for now sandbox dockerfiles to be spun up when needed
FROM docker

# Install python
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./runner ./runner

CMD [ "python3", "runner/main.py" ]