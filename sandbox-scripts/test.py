import urllib.request
import socket
import json
import os


def connect(dom):
    try:
        urllib.request.urlopen(dom)
        return True
    except:
        return False


def hostname_uses_loopback():
    try:
        address = socket.gethostbyname(socket.gethostname())
        return address == "127.0.0.1"
    except:
        return False


def writable(path):
    return os.access(path, os.W_OK)


def readable(path):
    return os.access(path, os.R_OK)


results = {"has_internet": connect('http://google.com'),
           "hostname_uses_loopback": hostname_uses_loopback(),
           "dirs": {path: {"readable": readable(path), "writable": writable(path)}
                    for path in ["/", "/exec", "/exec/test.py"]}}
print(json.dumps(results))
