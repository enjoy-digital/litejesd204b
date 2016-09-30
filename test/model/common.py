from collections import namedtuple

Control = namedtuple("Control", "value")

def swap_bytes(data, n):
    return int.from_bytes(data.to_bytes(n, byteorder="little"), byteorder="big")

def seed_to_data(seed, random=True):
    if random:
        return (seed * 0x31415979 + 1) & 0xffffffff
    else:
        return seed
