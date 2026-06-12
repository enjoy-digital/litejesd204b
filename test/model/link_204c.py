#
# This file is part of LiteJESD204B
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""JESD204C link layer reference models (bit-serial, independent of the HW implementation)."""

# Scrambler ----------------------------------------------------------------------------------------

class Scrambler64b66bModel:
    """Bit-serial x^58 + x^39 + 1 self-synchronous scrambler, MSB of each 64-bit word first."""
    def __init__(self):
        # S[0] is the most recent output bit; reset matches the HW state (bit 57 set).
        self.state = [0]*58
        self.state[57] = 1

    def scramble_word(self, word):
        out = 0
        for i in reversed(range(64)): # MSB first.
            d = (word >> i) & 1
            s = d ^ self.state[38] ^ self.state[57]
            out |= (s << i)
            self.state = [s] + self.state[:57]
        return out


class Descrambler64b66bModel:
    """Bit-serial x^58 + x^39 + 1 self-synchronous descrambler (feed-forward)."""
    def __init__(self):
        self.state = [0]*58
        self.state[57] = 1

    def descramble_word(self, word):
        out = 0
        for i in reversed(range(64)): # MSB first.
            s = (word >> i) & 1
            d = s ^ self.state[38] ^ self.state[57]
            out |= (d << i)
            self.state = [s] + self.state[:57]
        return out

# CRC-12 -------------------------------------------------------------------------------------------

class CRC12Model:
    """JESD204C CRC-12, 64 bits per step (word-level model of the parallel form).

    full = {state(12), feedback(64)}; feedback[j] = data[j] ^ full[12+j]
    ^ full[tap+j] for tap in (11, 10, 9, 4, 3) when tap+j <= 63; the registered
    state folds full as full[11:0] ^ full[10:0]<<1 ^ full[9:0]<<2 ^ full[8:0]<<3
    ^ full[3:0]<<8 ^ full[2:0]<<9.
    """
    def __init__(self):
        self.state = 0

    def reset(self):
        self.state = 0

    def update_word(self, word, init=False):
        state = 0 if init else self.state
        fb = [0]*76
        for i in range(12):
            fb[64+i] = (state >> i) & 1
        for j in reversed(range(64)):
            b = ((word >> j) & 1) ^ fb[12+j]
            for tap in [11, 10, 9, 4, 3]:
                if tap+j <= 63:
                    b ^= fb[tap+j]
            fb[j] = b
        full = 0
        for i in range(76):
            full |= fb[i] << i
        self.state = ((full & 0xfff)
            ^ ((full & 0x7ff) << 1)
            ^ ((full & 0x3ff) << 2)
            ^ ((full & 0x1ff) << 3)
            ^ ((full & 0x00f) << 8)
            ^ ((full & 0x007) << 9)) & 0xfff
        return self.state

# Sync word ----------------------------------------------------------------------------------------

def sync_word_crc12_mode(crc12, cmd=0, eoemb=0):
    """Build the 32-bit sync word (CRC-12 header mode), MSB transmitted first."""
    word = 0
    word |= 0b00001                     # [4:0]   EoMB sequence.
    word |= ((cmd >> 0) & 0x7)   << 5   # [7:5]   cmd[2:0].
    word |= 1                    << 8   # [8]     pilot.
    word |= (eoemb & 1)          << 9   # [9]     EoEMB.
    word |= 1                    << 10  # [10]    pilot.
    word |= ((cmd >> 3) & 0x1)   << 11  # [11]    cmd[3].
    word |= 1                    << 12  # [12]    pilot.
    word |= ((cmd >> 4) & 0x7)   << 13  # [15:13] cmd[6:4].
    word |= 1                    << 16  # [16]    pilot.
    word |= ((crc12 >> 0) & 0x7) << 17  # [19:17] crc[2:0].
    word |= 1                    << 20  # [20]    pilot.
    word |= ((crc12 >> 3) & 0x7) << 21  # [23:21] crc[5:3].
    word |= 1                    << 24  # [24]    pilot.
    word |= ((crc12 >> 6) & 0x7) << 25  # [27:25] crc[8:6].
    word |= 1                    << 28  # [28]    pilot.
    word |= ((crc12 >> 9) & 0x7) << 29  # [31:29] crc[11:9].
    return word


def sync_word_to_headers(word):
    """Sync word to the per-block 2-bit headers, MSB first; sync bit 1 -> 0b01."""
    headers = []
    for i in reversed(range(32)):
        bit = (word >> i) & 1
        headers.append(0b01 if bit else 0b10)
    return headers

# Bit-level 66b serializer (channel model) ---------------------------------------------------------

def serialize_blocks(blocks):
    """Serialize (data, header) blocks to a bit list, header first, LSB first (GT order)."""
    bits = []
    for data, header in blocks:
        for i in range(2):
            bits.append((header >> i) & 1)
        for i in range(64):
            bits.append((data >> i) & 1)
    return bits


def deserialize_blocks(bits, offset=0):
    """Deserialize a bit list into (data, header) blocks starting at an arbitrary bit offset."""
    blocks = []
    n = (len(bits) - offset)//66
    for b in range(n):
        chunk = bits[offset + 66*b:offset + 66*(b+1)]
        header = chunk[0] | (chunk[1] << 1)
        data = 0
        for i in range(64):
            data |= chunk[2+i] << i
        blocks.append((data, header))
    return blocks
