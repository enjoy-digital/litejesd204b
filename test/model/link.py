from litejesd204b.common import *


class Scrambler:
    """
    cf section 5.2.3
    """
    def __init__(self):
        self.state = [1]*15

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
    def __init__(self):
        self.state = [1]*15

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


def scramble_lane(lane):
    scrambler = Scrambler()
    scrambled_lane = []
    for frame in lane:
        scrambled_frame = []
        for octet in frame:
            scrambled_frame.append(scrambler.scramble(octet, 8))
        scrambled_lane.append(scrambled_frame)
    return scrambled_lane


def descramble_lane(lane):
    """
    cf section 5.2
    """
    descrambler = Descrambler()
    descrambled_lane = []
    for frame in lane:
        descrambled_frame = []
        for octet in frame:
            descrambled_frame.append(descrambler.descramble(octet, 8))
        descrambled_lane.append(descrambled_frame)
    return descrambled_lane


def scramble_lanes(lanes):
    scrambled_lanes = []
    for lane in lanes:
        scrambled_lanes.append(scramble_lane(lane))
    return scrambled_lanes


def descramble_lanes(lanes):
    descrambled_lanes = []
    for lane in lanes:
        descrambled_lanes.append(descramble_lane(lane))
    return descrambled_lanes


def insert_alignment_characters(frames_per_multiframe, scrambled, lanes):
    """
    -lanes: Lanes' octets organized in frames
            lanes[i][j][k]: octet k of frame j of lane i

    cf section 5.3.3.4
    """
    new_lanes = []
    for lane in lanes:
        new_lane = []
        last_dn = -1
        for n, frame in enumerate(lane):
            dn = frame[-1]
            last_frame_of_multiframe = ((n+1)%frames_per_multiframe == 0)

            if scrambled:
                if (dn == 0x7c) & last_frame_of_multiframe:
                    dn = is_control_character | control_characters["A"]
                if dn == 0xfc:
                    dn = is_control_character | control_characters["F"]
            else:
                if dn == last_dn:
                    if last_frame_of_multiframe:
                        dn = is_control_character | control_characters["A"]
                    else:
                        dn = is_control_character | control_characters["F"]

            frame[-1] = dn
            last_dn = dn

            new_lane.append(frame)

        new_lanes.append(new_lane)

    return new_lanes


def remove_alignment_characters(frames_per_multiframe, scrambled, lanes):
    """
    -lanes: Lanes' octets organized in frames
            lanes[i][j][k]: octet k of frame j of lane i

    cf section 5.3.3.4
    """
    new_lanes = []
    for lane in lanes:
        new_lane = []
        last_dn = -1
        for n, frame in enumerate(lane):
            dn = frame[-1]
            last_frame_of_multiframe = ((n+1)%frames_per_multiframe == 0)

            if dn & is_control_character:
                dn = dn & 0xff
                if scrambled:
                    if dn == control_characters["A"]:
                        dn = 0x7c
                    elif control_characters["F"]:
                        dn = 0xfc
                else:
                    if dn == control_characters["A"]:
                        dn = last_dn
                    elif dn == control_characters["F"]:
                        dn = last_dn

            frame[-1] = dn
            last_dn = dn

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
        new_lanes = remove_alignment_characters(self.frames_per_multiframe,
                                                self.scrambled,
                                                lanes)
        if self.scrambled:
            new_lanes = descramble_lanes(lanes)
        return new_lanes
