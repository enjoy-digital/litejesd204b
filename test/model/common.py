from collections import namedtuple

Control = namedtuple("Control", "value")

def seed_to_data(seed, random=True):
    if random:
        return (seed * 0x31415979 + 1) & 0xffffffff
    else:
        return seed
