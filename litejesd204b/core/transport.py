from math import ceil

from litex.gen import *

from litejesd204b.common import *

from litex.soc.interconnect import stream


class TransportTX(Module):
    """Transport Tx layer
    """
    def __init__(self,
            transport_settings,
            physical_settings,
            converter_dw,
            lane_dw):

        # parameters
        nconverters = physical_settings.m
        nlanes = physical_settings.l
        sample_per_frame = transport_settings.s

        nsamples = converter_dw//physical_settings.n
        nibbles_per_word = ceil(physical_settings.n//4)
        octets_per_lane = sample_per_frame*nibbles_per_word//2
        
        self.sink = stream.Endpoint(transport_layout(converter_dw, nconverters))
        self.source = stream.Endpoint(transport_layout(lane_dw, nlanes))

        # # #

        # check input/output data width consistency (FIXME)
        assert converter_dw*nconverters == lane_dw*nlanes

        n = 0
        m = 0

        while n < nsamples:
            # frame's samples
            frame_samples = []
            for i in range(sample_per_frame):
                for j in range(nconverters):
                    converter_data = getattr(self.sink, "data"+str(j))
                    sample = Signal(physical_settings.n)
                    self.comb += sample.eq(converter_data[(n+i)*physical_settings.n:])
                    frame_samples.append(sample)
            n += sample_per_frame

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
                    self.comb += lane_data[8*(m+j):8*(m+j+1)].eq(octet)

            m += octets_per_lane

        self.comb += [
            self.source.valid.eq(self.sink.valid),
            self.sink.ready.eq(self.source.ready)
        ]
