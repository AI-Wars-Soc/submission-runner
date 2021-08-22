from cuwais.config import config_file

with open("/run/secrets/secret_key") as secrets_file:
    secret = "".join(secrets_file.readlines())
    SECRET_KEY = secret

DEBUG = config_file.get("debug")
PROFILE = config_file.get("profile")
