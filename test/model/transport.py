from math import ceil

from litejesd204b.common import *


class TransportLayer:
    def __init__(self, settings):
        self.settings = settings

    def map_samples_to_lanes_octets(self, nlanes, nconverters, nbits, samples):
        """
        inputs:
        -nlanes: Number of lanes per converter
        -nconverters: Number of converters
        -nbits: Number of convertion bits
        -samples: Samples from converters:
                  samples[n][i] = sample i of converter n
        output:
        lanes: Samples mapped to lanes
               lanes[n][i] = frame i of lane n
        """
        assert nconverters == len(samples)

        samples_per_frame = self.settings.s
        lanes_octets = [[]]*nlanes
        n = 0

        while n < len(samples[0]):
            # frame's samples
            frame_samples = []
            for i in range(samples_per_frame):
                for j in range(nconverters):
                    frame_samples.append(samples[j][n+i])
            n += samples_per_frame

            # frame's words
            frame_words = frame_samples # no control bits

            # frame's nibbles
            nibbles_per_word = ceil(nbits//4)
            frame_nibbles = []
            for word in frame_words:
                for i in reversed(range(nibbles_per_word)):
                    frame_nibbles.append((word>>4*i) & 0xf)

            # frame's octets
            frame_octets = []
            for i in range(len(frame_nibbles)//2):
                octet = (frame_nibbles[2*i]<<4) + frame_nibbles[2*i+1]
                frame_octets.append(octet)

            # lanes' octets for a frame
            octets_per_lane = len(frame_octets)//nlanes
            for i in range(nlanes):
                frame_lane_octets = frame_octets[i*octets_per_lane:
                                                 (i+1)*octets_per_lane]
                lanes_octets[i] = lanes_octets[i] + frame_lane_octets

        return lanes_octets


if __name__ == "__main__":
    transport_settings = LiteJESD204BTransportSettings(f=2, s=1, k=16, cs=1)
    transport = TransportLayer(transport_settings)

    nlanes = 4
    nconverters = 4

    samples = []
    for i in range(nconverters):
        samples.append([j+i*256 for j in range(8)])
    lanes_octets = transport.map_samples_to_lanes_octets(nlanes, nconverters, 16, samples)

    # debug
    for converter_samples in samples:
        print(converter_samples)
    for lane_octets in lanes_octets:
        print(lane_octets)
