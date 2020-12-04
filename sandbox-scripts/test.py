import json
import os
import platform
import socket
import urllib.request


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


def get_mem():
    meminfo = dict((i.split()[0].rstrip(':'), int(i.split()[1])) for i in open('/proc/meminfo').readlines())
    return meminfo['MemTotal']


def get_system_info():
    try:
        info = {'platform': platform.system(), 'platform-release': platform.release(),
                'platform-version': platform.version(), 'architecture': platform.machine(),
                'hostname': socket.gethostname(), 'processor': platform.processor(),
                'ram': str(round(get_mem() / 1024.0)) + " MB",
                'cpus': os.cpu_count()}
        return info
    except Exception as e:
        return e


results = {"has_internet": connect('http://google.com'),
           "hostname_uses_loopback": hostname_uses_loopback(),
           "dirs": {path: {"readable": readable(path), "writable": writable(path)}
                    for path in ["/", "/exec", "/exec/test.py"]},
           "system": get_system_info(),
           "user": {"uid": os.getuid()},
           "process": {"cwd": os.getcwd(), "pid": os.getpid()}}
print(json.dumps(results))
