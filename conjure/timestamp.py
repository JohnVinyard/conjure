import time
import binascii
import os


def timestamp_id():
    b = hex(int(time.time() * 1e6)).encode() + binascii.hexlify(os.urandom(8))
    return b[2:]
