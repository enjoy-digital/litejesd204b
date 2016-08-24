from litejesd204b.common import *

class LinkLayer:
    def __init__(self, scrambled=False):
        self.scrambled = False

    def insert_alignment_characters(self, lanes):
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
    link = LinkLayer(None)
    lanes = [
        [[0, 0], [0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [0, 6], [0, 7]],
        [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
        [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
        [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]],
    ]
    lanes = link.insert_alignment_characters(lanes)
    print(lanes)
    lanes = link.remove_alignment_characters(lanes)
    print(lanes)
