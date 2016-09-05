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
    """
    cf section 5.2.3
    """
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


def scramble(lane):
    """
    cf section 5.2
    """
    pass


def descramble(lane):
    """
    cf section 5.2
    """
    pass


class LinkLayer:
    def __init__(self, frames_per_multiframe, scrambled=False):
        self.frames_per_multiframe = frames_per_multiframe
        self.scrambled = False

    def insert_alignment_characters(self, lanes):
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
                last_frame_of_multiframe = ((n+1)%self.frames_per_multiframe == 0)

                if self.scrambled:
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

    def remove_alignment_characters(self, lanes):
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
                last_frame_of_multiframe = ((n+1)%self.frames_per_multiframe == 0)

                if dn & is_control_character:
                    dn = dn & 0xff
                    if self.scrambled:
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


if __name__ == "__main__":
    print("scrambler test")
    scrambler = Scrambler()
    descrambler = Descrambler()
    errors = 0
    for i in range(128):
        if descrambler.descramble(scrambler.scramble(i, 32), 32) != i:
            errors += 1
    print("errors: {:d}".format(errors))

    print("link test")
    link = LinkLayer(4, False)
    lanes = [
        [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]],
        [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
        [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
        [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]],
    ]
    print(lanes)
    lanes = link.insert_alignment_characters(lanes)
    print(lanes)
    lanes = link.remove_alignment_characters(lanes)
    print(lanes)
