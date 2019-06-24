# This file is Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

from collections import namedtuple

Control = namedtuple("Control", "value")

def swap_bytes(data, n):
    return int.from_bytes(data.to_bytes(n, byteorder="little"), byteorder="big")

def seed_to_data(seed, random=True):
	return (seed * 0x31415979 + 1) & 0xffffffff if random else seed
