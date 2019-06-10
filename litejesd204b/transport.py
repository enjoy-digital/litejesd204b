from math import ceil

from migen import *


def seed_to_data(seed, random=True):
    return ((seed + 1)*0x31415979 + 1) & 0xffff if random else seed


class LiteJESD204BTransportTX(Module):
    """Transport TX layer
    inputs:
    - jesd_settings:        JESD204B settings
    - converter_data_width: Converters' data width
    cf section 5.1.3
    """
    def __init__(self, jesd_settings, converter_data_width):
        # compute parameters
        samples_per_clock = converter_data_width//jesd_settings.phy.n
        samples_per_frame = jesd_settings.transport.s
        lane_data_width = (samples_per_clock*
                           jesd_settings.phy.np*
                           jesd_settings.nconverters)//jesd_settings.nlanes

        # endpoints
        self.sink = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])
        self.source = Record([("lane"+str(i), lane_data_width)
            for i in range(jesd_settings.nlanes)])

        # # #

        current_sample = 0
        current_octet = 0
        while current_sample < samples_per_clock:
            # frame's samples
            frame_samples = []
            for j in range(jesd_settings.nconverters):
                for i in range(samples_per_frame):
                    converter_data = getattr(self.sink, "converter"+str(j))
                    sample = Signal(jesd_settings.phy.n)
                    self.comb += sample.eq(
                        converter_data[(current_sample+i)*jesd_settings.phy.n:
                        (current_sample+i+1)*jesd_settings.phy.n])
                    frame_samples.append(sample)

            # frame's words
            frame_words = frame_samples # no control bits

            # frame's nibbles
            frame_nibbles = []
            for word in frame_words:
                for i in reversed(range(jesd_settings.nibbles_per_word)):
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
            for i in range(jesd_settings.nlanes):
                frame_lane_octets = frame_octets[
                    i*jesd_settings.octets_per_lane:
                    (i+1)*jesd_settings.octets_per_lane]
                lane_data = getattr(self.source, "lane"+str(i))
                for j, octet in enumerate(frame_lane_octets):
                    self.comb += lane_data[
                        8*(current_octet+j):
                        8*(current_octet+j+1)].eq(octet)

            current_sample += samples_per_frame
            current_octet += jesd_settings.octets_per_lane


class LiteJESD204BTransportRX(Module):
    """Transport RX layer
    inputs:
    - jesd_settings:        JESD204B settings
    - converter_data_width: Converters' data width
    cf section 5.1.3
    """
    def __init__(self, jesd_settings, converter_data_width):
        # compute parameters
        samples_per_clock = converter_data_width//jesd_settings.phy.n
        samples_per_frame = jesd_settings.transport.s
        lane_data_width = (samples_per_clock*
                           jesd_settings.phy.np*
                           jesd_settings.nconverters)//jesd_settings.nlanes

        # endpoints
        self.sink = Record([("lane"+str(i), lane_data_width)
            for i in range(jesd_settings.nlanes)])
        self.source = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        current_sample = 0
        current_octet = 0
        while current_sample < samples_per_clock:
            # frame's octets
            frame_octets = []
            for i in range(jesd_settings.nlanes):
                frame_lane_octets = []
                lane_data = getattr(self.sink, "lane"+str(i))
                for j in range(jesd_settings.octets_per_lane):
                    frame_lane_octets.append(lane_data[
                        8*(current_octet+j):
                        8*(current_octet+j+1)])
                frame_octets += frame_lane_octets

            # frame's nibbles
            frame_nibbles = []
            for octet in frame_octets:
                for j in reversed(range(2)):
                    frame_nibbles.append(octet[4*j:4*(j+1)])

            # frame's words
            frame_words = []
            for j in range(jesd_settings.nconverters):
                for i in range(samples_per_frame):
                    word = Signal(jesd_settings.nibbles_per_word*4)
                    for k in range(jesd_settings.nibbles_per_word):
                        self.comb += word[4*k:4*(k+1)].eq(frame_nibbles.pop())
                    frame_words.append(word)

            # frame's samples
            frame_samples = frame_words # no control bits

            # converters' samples for a frame
            for j in range(jesd_settings.nconverters):
                for i in range(samples_per_frame):
                    converter_data = getattr(self.source, "converter"+str(j))
                    self.comb += converter_data[
                        (current_sample+i)*jesd_settings.phy.n:
                        (current_sample+i+1)*jesd_settings.phy.n].eq(frame_samples.pop())

            current_sample += samples_per_frame
            current_octet += jesd_settings.octets_per_lane


class LiteJESD204BSTPLGenerator(Module):
    """Simple Transport Layer Pattern Generator
    cf section 5.1.6.2
    """
    def __init__(self, jesd_settings, converter_data_width):
        self.source = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        samples_per_clock = converter_data_width//jesd_settings.phy.n
        samples_per_frame = jesd_settings.transport.s

        for i in range(jesd_settings.nconverters):
            converter = getattr(self.source, "converter"+str(i))
            for j in range(samples_per_clock):
                data = seed_to_data((i << 8) | j%samples_per_frame, True)
                self.comb += converter[j*jesd_settings.phy.n:
                                       (j+1)*jesd_settings.phy.n].eq(data)
