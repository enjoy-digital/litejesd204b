from math import ceil

from litex.gen import *


class LiteJESD204BTransportTX(Module):
    """Transport Tx layer
    inputs:
    - jesd_settings:        JESD204B settings
    - converter_data_width: Converters' data width
    cf section 5.1.3
    """
    def __init__(self, jesd_settings, converter_data_width):
        # compute parameters
        nconverters = jesd_settings.phy.m
        nlanes = jesd_settings.phy.l

        samples_per_clock = converter_data_width//jesd_settings.phy.n
        samples_per_frame = jesd_settings.transport.s

        nibbles_per_word = ceil(jesd_settings.phy.np//4)
        octets_per_frame = samples_per_frame*nibbles_per_word//2
        octets_per_lane = octets_per_frame*nconverters//nlanes
        assert octets_per_lane > 0

        lane_data_width = samples_per_clock*jesd_settings.phy.np*nconverters//nlanes

        self.converter_data_width = converter_data_width
        self.lane_data_width = lane_data_width

        # endpoints
        self.sink = Record([("converter"+str(i), converter_data_width) for i in range(nconverters)])
        self.source = Record([("lane"+str(i), lane_data_width) for i in range(nlanes)])

        # # #

        current_sample = 0
        current_octet = 0
        while current_sample < samples_per_clock:
            # frame's samples
            frame_samples = []
            for i in range(samples_per_frame):
                for j in range(nconverters):
                    converter_data = getattr(self.sink, "converter"+str(j))
                    sample = Signal(jesd_settings.phy.n)
                    self.comb += sample.eq(converter_data[(current_sample+i)*jesd_settings.phy.n:
                                                          (current_sample+i+1)*jesd_settings.phy.n])
                    frame_samples.append(sample)

            # frame's words
            frame_words = frame_samples # no control bits

            # frame's nibbles
            frame_nibbles = []
            for word in frame_words:
                for i in reversed(range(nibbles_per_word)):
                    nibble = Signal(4)
                    self.comb += nibble.eq(word[4*i:4*(i+1)])
                    frame_nibbles.append(nibble)

            # frame's octets
            frame_octets = []
            for i in range(len(frame_nibbles)//2):
                octet = Signal(8)
                self.comb += octet.eq(Cat(frame_nibbles[2*i+1],
                                          frame_nibbles[2*i]))
                frame_octets.append(octet)

            # lanes' octets for a frame
            for i in range(nlanes):
                frame_lane_octets = frame_octets[i*octets_per_lane:
                                                (i+1)*octets_per_lane]
                lane_data = getattr(self.source, "lane"+str(i))
                for j, octet in enumerate(frame_lane_octets[::-1]):
                    self.comb += lane_data[8*(current_octet+j):8*(current_octet+j+1)].eq(octet)

            current_sample += samples_per_frame
            current_octet += octets_per_lane
