from litejesd204b.common import *


class TransportLayer:
    def __init__(self, settings):
        self.settings = settings

    def map_samples_to_lanes(self, l, m, samples):
        # see spec p45
        assert m == len(samples[0])
        s = self.settings.s

        lanes_data = []

        while len(samples):
            # frame samples
            frame_samples = []
            for i in range(s):
                for c in range(m):
                    frame_samples.append(samples[i][c])
            for i in range(s):
                samples.pop(0)

            # frame words, XXX append control bits?
            frame_words = frame_samples

            # frame nibble groups, XXX extend to nibble boundary?
            frame_nibble_groups = frame_words

            # frame octets
            frame_octets = []
            for nibble_group in frame_nibble_groups:
                for i in range(2): # XXX should be np//8
                    frame_octets.append((nibble_group >> 8*i) & 0xff)

            # map octets to lanes
            lanes_octets = []
            for l in range(m):
                octets_per_lane = len(frame_octets)//m
                lanes_octets.append(frame_octets[l*octets_per_lane:(l+1)*octets_per_lane])

            lanes_data.append(lanes_octets)

        return lanes_data


if __name__ == "__main__":
    transport_settings = LiteJESD204BTransportSettings(f=2, s=1, k=16, cs=1)
    transport = TransportLayer(transport_settings)

    l = 4
    m = 4

    samples = []
    for i in range(32):
        samples.append([i+j*256 for j in range(m)])
    lanes_data = transport.map_samples_to_lanes(l, m, samples)
    for data in lanes_data:
        print(data)
