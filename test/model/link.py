#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from litejesd204b.common import control_characters

from test.model.common import Control

# scrambling
class Scrambler:
    """
    cf section 5.2.3
    """
    def __init__(self, seed=0x7f80):
        self.state = [0]*15
        for i in range(15):
            if (seed >> (14-i)) & 0x1:
                self.state[i] = 1

    def shift(self, d15):
        s15 = (d15 ^ self.state[1] ^ self.state[0]) & 0x1
        self.state.pop(0)
        self.state.append(s15)
        return s15

    def scramble(self, data, n):
        v = 0
        for i in range(n):
            v <<= 1
            v |= self.shift((data >> (n-1)) & 0x1)
            data <<= 1
        return v


class Descrambler:
    """
    cf section 5.2
    """
    def __init__(self, seed=0x7f80):
        self.state = [0]*15
        for i in range(15):
            if (seed >> (14-i)) & 0x1:
                self.state[i] = 1

    def shift(self, s15):
        d15 = (s15 ^ self.state[1] ^ self.state[0]) & 0x1
        self.state.pop(0)
        self.state.append(s15)
        return d15

    def descramble(self, data, n):
        v = 0
        for i in range(n):
            v <<= 1
            v |= self.shift((data >> (n-1)) & 0x1)
            data <<= 1
        return v


def scramble_lanes(lanes):
    scrambled_lanes = []
    for lane in lanes:
        scrambler = Scrambler()
        scrambled_lane = []
        for frame in lane:
            scrambled_frame = []
            for octet in frame:
                scrambled_frame.append(scrambler.scramble(octet, 8))
            scrambled_lane.append(scrambled_frame)
        scrambled_lanes.append(scrambled_lane)
    return scrambled_lanes


def descramble_lanes(lanes):
    descrambled_lanes = []
    for lane in lanes:
        descrambler = Descrambler()
        descrambled_lane = []
        for frame in lane:
            descrambled_frame = []
            for octet in frame:
                descrambled_frame.append(descrambler.descramble(octet, 8))
            descrambled_lane.append(descrambled_frame)
        descrambled_lanes.append(descrambled_lane)
    return descrambled_lanes


# alignment characters
def insert_alignment_characters(frames_per_multiframe, scrambled, lanes):
    """
    -lanes: Lanes' octets organized in frames
            lanes[i][j][k]: octet k of frame j of lane i

    cf section 5.3.3.4
    """
    new_lanes = []
    for lane in lanes:
        new_lane = []
        for n, frame in enumerate(lane):
            new_frame = [frame[i] for i in range(len(frame))]
            dn = new_frame[-1]
            last_frame_of_multiframe = ((n+1)%frames_per_multiframe == 0)

            if scrambled:
                if (dn == control_characters["A"]) & last_frame_of_multiframe:
                    dn = Control(dn)
                if (dn == control_characters["F"]) & ~last_frame_of_multiframe:
                    dn = Control(dn)
            else:
                raise NotImplementedError

            new_frame[-1] = dn

            new_lane.append(new_frame)

        new_lanes.append(new_lane)

    return new_lanes


def replace_alignment_characters(frames_per_multiframe, scrambled, lanes):
    """
    -lanes: Lanes' octets organized in frames
            lanes[i][j][k]: octet k of frame j of lane i

    cf section 5.3.3.4
    """
    new_lanes = []
    for lane in lanes:
        new_lane = []
        for n, frame in enumerate(lane):
            dn = frame[-1]
            last_frame_of_multiframe = ((n+1)%frames_per_multiframe == 0)

            if isinstance(dn, Control):
                if scrambled:
                    dn = dn.value
                else:
                    raise NotImplementedError

            frame[-1] = dn

            new_lane.append(frame)

        new_lanes.append(new_lane)

    return new_lanes


class LinkLayer:
    def __init__(self, frames_per_multiframe, scrambled=False):
        self.frames_per_multiframe = frames_per_multiframe
        self.scrambled = scrambled

    def encode(self, lanes):
        new_lanes = []
        if self.scrambled:
            new_lanes = scramble_lanes(lanes)
        new_lanes = insert_alignment_characters(self.frames_per_multiframe,
                                                self.scrambled,
                                                new_lanes)
        return new_lanes

    def decode(self, lanes):
        new_lanes = replace_alignment_characters(self.frames_per_multiframe,
                                                self.scrambled,
                                                lanes)
        new_lanes = lanes
        if self.scrambled:
            new_lanes = descramble_lanes(lanes)
        return new_lanes
