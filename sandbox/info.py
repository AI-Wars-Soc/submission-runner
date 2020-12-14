import json
import os
import platform
import socket
import urllib.request
import numpy as np
from time import time
from shared.messages import Sender


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


def numpy_speed_test():
    np_results = {}

    # From https://gist.github.com/markus-beuckelmann/8bc25531b11158431a5b09a45abd6276
    # Let's take the randomness out of random numbers (for reproducibility)
    np.random.seed(0)

    size = 2048
    A, B = np.random.random((size, size)), np.random.random((size, size))
    C, D = np.random.random((size * 128,)), np.random.random((size * 128,))
    E = np.random.random((int(size / 2), int(size / 4)))
    F = np.random.random((int(size / 2), int(size / 2)))
    F = np.dot(F, F.T)
    G = np.random.random((int(size / 2), int(size / 2)))

    # Matrix multiplication
    N = 20
    t = time()
    for i in range(N):
        np.dot(A, B)
    delta = time() - t
    np_results["dot_matrix"] = {"size": (size, size), "time": 1e3 * delta/N}
    del A, B

    # Vector multiplication
    N = 5000
    t = time()
    for i in range(N):
        np.dot(C, D)
    delta = time() - t
    np_results["dot_vector"] = {"size": size * 128, "time": 1e3 * delta/N}
    del C, D

    # Singular Value Decomposition (SVD)
    N = 3
    t = time()
    for i in range(N):
        np.linalg.svd(E, full_matrices=False)
    delta = time() - t
    np_results["svd"] = {"size": (size / 2, size / 4), "time": 1e3 * delta/N}
    del E

    # Cholesky Decomposition
    N = 3
    t = time()
    for i in range(N):
        np.linalg.cholesky(F)
    delta = time() - t
    np_results["cholesky"] = {"size": (size / 2, size / 4), "time": 1e3 * delta/N}

    # Eigendecomposition
    t = time()
    for i in range(N):
        np.linalg.eig(G)
    delta = time() - t
    np_results["eigendecomposition"] = {"size": (size / 2, size / 4), "time": 1e3 * delta/N}

    return np_results


print("Start Print")
sender = Sender()
results = {"has_internet": connect('http://google.com'),
           "hostname_uses_loopback": hostname_uses_loopback(),
           "dirs": {path: {"readable": readable(path), "writable": writable(path)}
                    for path in ["/", "/exec", "/exec/test.py"]},
           "system": get_system_info(),
           "user": {"uid": os.getuid()},
           "process": {"cwd": os.getcwd(), "pid": os.getpid()},
           "numpy_benchmark": numpy_speed_test()}
print("Mid Print")
sender.send_result(results)
print("End Print")
