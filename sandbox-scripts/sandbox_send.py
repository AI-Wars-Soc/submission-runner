import random
import json

# Note: As much as it would be nice for all of these methods to be in a class,
# see https://stackoverflow.com/questions/328851/printing-all-instances-of-a-class
# Also note: If you are looking through the source code for a way to hack the system,
# congratulations! This is probably where you want to look. Now try not to get caught...


def gen_key():
    key = json.dumps({"code": hex(random.randint(-10000000, 10000000))})
    print("\nNEW_KEY_EVENT: {};;".format(key), flush=True)
    return key


def deliver(key, message):
    print("\nMESSAGE_EVENT: {}; {};;".format(key, message), flush=True)
