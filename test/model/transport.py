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
               lanes[n][i] = octet i of lane n
        """
        assert nconverters == len(samples)

        samples_per_frame = self.settings.s
        nibbles_per_word = ceil(nbits//4)
        octets_per_lane = samples_per_frame*nibbles_per_word//2

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
            for i in range(nlanes):
                frame_lane_octets = frame_octets[i*octets_per_lane:
                                                 (i+1)*octets_per_lane]
                lanes_octets[i] = lanes_octets[i] + frame_lane_octets

        return lanes_octets

    def map_lanes_octets_to_samples(self, nlanes, nconverters, nbits, lanes_octets):
        """
        inputs:
        -nlanes: Number of lanes per converter
        -nconverters: Number of converters
        -nbits: Number of convertion bits
        -lanes: Samples mapped to lanes
                lanes[n][i] = octet i of lane n
        output:
        -samples: Samples from converters:
                  samples[n][i] = sample i of converter n
        """
        assert nlanes == len(lanes_octets)

        samples_per_frame = self.settings.s
        nibbles_per_word = ceil(nbits//4)
        octets_per_lane = samples_per_frame*nibbles_per_word//2

        samples = [[]]*nconverters
        n = 0

        while n < len(lanes_octets[0]):
            # frame's octets
            frame_octets = []
            for i in range(nlanes):
                frame_octets = frame_octets + lanes_octets[i][n:n+octets_per_lane]
            n += octets_per_lane

            # frame's nibbles
            frame_nibbles = []
            for octet in frame_octets:
                frame_nibbles = frame_nibbles + [(octet>>4) & 0xf, octet & 0xf]

            # frame's words
            frame_words = []
            for i in range(len(frame_nibbles)//nibbles_per_word):
                word = 0
                for j in range(nibbles_per_word):
                    word |= (frame_nibbles[i*nibbles_per_word+j] << 4*(3-j))
                frame_words.append(word)

            # frame's samples
            frame_samples = frame_words # no control bits

            # converters' samples for a frame
            for i in range(nconverters):
                converter_samples = frame_samples[i*samples_per_frame:
                                                 (i+1)*samples_per_frame]
                samples[i] = samples[i] + converter_samples

        return samples


if __name__ == "__main__":
    transport_settings = LiteJESD204BTransportSettings(f=2, s=1, k=16, cs=1)
    transport = TransportLayer(transport_settings)

    nlanes = 4
    nconverters = 4

    samples = []
    for i in range(nconverters):
        samples.append([j+i*256 for j in range(8)])

    lanes_octets = transport.map_samples_to_lanes_octets(nlanes, nconverters, 16, samples)
    reverted_samples = transport.map_lanes_octets_to_samples(nlanes, nconverters, 16, lanes_octets)

    # debug
    print("-"*80)
    print(samples)
    print("-"*80)
    print(lanes_octets)
    print("-"*80)
    print(reverted_samples)
