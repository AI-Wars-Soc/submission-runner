# Dockerfile for sandbox api, allowing for now sandbox dockerfiles to be spun up when needed
FROM pypy:3

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src .

CMD [ "pypy", "src/main.py" ]