from litejesd204b.common import *


class LinkLayer:
    def __init__(self, frames_per_multiframe, scrambled=False):
        self.frames_per_multiframe = frames_per_multiframe
        self.scrambled = False

    def insert_alignment_characters(self, lanes):
        """
        -lanes: Lanes' octets organized in frames
                lanes[i][j][k]: octet k of frame j of lane i
        """
        new_lanes = []
        for lane in lanes:
            new_lane = []
            last_dn = -1
            n = 0
            for frame in lane:
                dn = frame[-1]
                if n%self.frames_per_multiframe == (self.frames_per_multiframe-1):
                    last_frame_of_multiframe = True
                else:
                    last_frame_of_multiframe = False

                if self.scrambled:
                    if dn == 0x7c:
                        if last_frame_of_multiframe:
                            dn = control_characters["A"]
                    if dn == 0xfc:
                        dn = control_characters["F"]
                else:
                    if dn == last_dn:
                        if last_frame_of_multiframe:
                            dn = control_characters["A"]
                        else:
                            dn = control_characters["F"]
                frame[-1] = dn
                last_dn = dn
                n = n + 1

                new_lane.append(frame)

            new_lanes.append(new_lane)

        return new_lanes

    def remove_alignment_characters(self, lanes):
        """
        -lanes: Lanes' octets organized in frames
                lanes[i][j][k]: octet k of frame j of lane i
        """
        for lane in lanes:
            last_frame_of_multiframe = False
            for frame in lane:
                if self.scrambled:
                   pass
                else:
                   pass

        return lanes


if __name__ == "__main__":
    link = LinkLayer(4, False)
    lanes = [
        [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]],
        [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
        [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
        [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]],
    ]
    lanes = link.insert_alignment_characters(lanes)
    print(lanes)
    lanes = link.remove_alignment_characters(lanes)
    print(lanes)
