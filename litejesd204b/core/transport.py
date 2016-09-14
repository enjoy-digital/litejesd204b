from math import ceil

from litex.gen import *
from litex.soc.interconnect import stream

from litejesd204b.common import *


class TransportTX(Module):
    """Transport Tx layer
    inputs:
    - transport_settings:   JESD204B transport layer settings
    - physical_settings:    JESD204B physical layer settings
    - converter_data_width: Converters' data width
    cf section 5.1.3
    """
    def __init__(self, transport_settings, physical_settings, converter_data_width):
        # compute parameters
        nconverters = physical_settings.m
        nlanes = physical_settings.l

        samples_per_clock = converter_data_width//physical_settings.n
        samples_per_frame = transport_settings.s
        
        nibbles_per_word = ceil(physical_settings.np//4)
        octets_per_lane = samples_per_frame*nibbles_per_word//2

        lane_data_width = samples_per_clock*physical_settings.np*nconverters//nlanes
            
        # endpoints
        self.sink = stream.Endpoint(transport_layout(converter_data_width, nconverters))
        self.source = stream.Endpoint(transport_layout(lane_data_width, nlanes))

        # # #

        # ctrl
        self.comb += [
            self.source.valid.eq(self.sink.valid),
            self.sink.ready.eq(self.source.ready)
        ]

        # data (mapping)
        current_sample = 0
        current_octet = 0
        while current_sample < samples_per_clock:
            # frame's samples
            frame_samples = []
            for i in range(samples_per_frame):
                for j in range(nconverters):
                    converter_data = getattr(self.sink, "data"+str(j))
                    sample = Signal(physical_settings.n)
                    self.comb += sample.eq(converter_data[(current_sample+i)*physical_settings.n:])
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
                lane_data = getattr(self.source, "data"+str(i))
                for j, octet in enumerate(frame_lane_octets):
                    self.comb += lane_data[8*(current_octet+j):8*(current_octet+j+1)].eq(octet)

            current_sample += samples_per_frame
            current_octet += octets_per_lane
