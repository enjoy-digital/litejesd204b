#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from math import ceil


def short_test_pattern(nconverters, samples_per_frame, repeats):
    """
    Generates the short transport layer test pattern:
    - one frame duration
    - repeated continuously
    - each sample should have a unique value that can be identified with the
      position of the sample in the user data format.

    cf section 5.1.6.2
    """
    samples = []
    for c in range(nconverters):
        converter_samples = []
        for r in range(repeats):
            for s in range(samples_per_frame):
                # unique id = converter_id*16 + sample_id
                converter_samples.append(c*16+s)
        samples.append(converter_samples)
    return samples


def long_test_pattern(nconverters, nbits, samples_per_frame, frame_per_multiframe, repeats):
    """
    Generates the long transport layer test pattern:
    - duration of max(nconverters*samples_per_frame+2, 4) rounded up to lowest
      number of full multiframes.
    - repeated continuously
    - frame 0: Converter ID + 1
    - frame 1: Samples ID + 1
    - frame N: MSB bit set to 1

    limitations:
    - control and tail bits no supported

    cf section 5.1.6.3
    """
    nframes = min(max(nconverters*samples_per_frame+2, 4), frame_per_multiframe)

    samples = []
    for c in range(nconverters):
        converter_samples = []
        for r in range(repeats):
            for f in range(nframes):
                for s in range(samples_per_frame):
                    # converter id + 1
                    if f == 0:
                        converter_samples.append(c+1)
                    # sample id + 1
                    elif f == 1:
                        converter_samples.append(s+1)
                    # sample's msb bit set to 1
                    else:
                        converter_samples.append(2**(nbits-1))
        samples.append(converter_samples)
    return samples


def samples_to_lanes(samples_per_frame, nlanes, nconverters, nbits, samples):
    """
    inputs:
    - samples_per_frame: Number of samples per frame
    - nlanes:            Number of lanes per converter
    - nconverters:       Number of converters
    - nbits:             Number of convertion bits
    - samples:           Samples from converters:
                         samples[i][j]: sample j of converter i
    output:
    - lanes: Lanes' octets organized in frames
             lanes[i][j][k]: octet k of frame j of lane i

    cf section 5.1.3
    """
    assert nconverters == len(samples)

    nibbles_per_word = ceil(nbits//4)
    octets_per_frame = samples_per_frame*nibbles_per_word//2
    octets_per_lane = octets_per_frame*nconverters//nlanes
    assert octets_per_lane > 0

    lanes = [[]]*nlanes
    n = 0

    while n < len(samples[0]):
        # frame's samples
        frame_samples = []
        for j in range(nconverters):
            for i in range(samples_per_frame):
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
            lanes[i] = lanes[i] + [frame_lane_octets]

    return lanes


def lanes_to_samples(samples_per_frame, nlanes, nconverters, nbits, lanes):
    """
    inputs:
    - samples_per_frame: Number of samples per frame
    - nlanes:            Number of lanes per converter
    - nconverters:       Number of converters
    - nbits:             Number of convertion bits
    - lanes:             Lanes' octets organized in frames
                         lanes[i][j][k]: octet k of frame j of lane i
    output:
    - samples: Samples from converters:
               samples[i][j]: sample j of converter i

    cf section 5.1.3
    """
    assert nlanes == len(lanes)

    nibbles_per_word = ceil(nbits//4)
    octets_per_frame = samples_per_frame*nibbles_per_word//2
    octets_per_lane = octets_per_frame*nconverters//nlanes
    assert octets_per_lane > 0

    samples = [[]]*nconverters
    n = 0

    while n < len(lanes[0]):
        # frame's octets
        frame_octets = []
        for i in range(nlanes):
            frame_octets = frame_octets + lanes[i][n]
        n += 1

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


class TransportLayer:
    def __init__(self, jesd_settings):
        self.jesd_settings = jesd_settings

    def encode(self, samples):
        return samples_to_lanes(self.jesd_settings.transport.s,
                                self.jesd_settings.phy.l,
                                self.jesd_settings.phy.m,
                                self.jesd_settings.phy.n,
                                samples)

    def decode(self, lanes):
        return lanes_to_samples(self.jesd_settings.transport.s,
                                self.jesd_settings.phy.l,
                                self.jesd_settings.phy.m,
                                self.jesd_settings.phy.n,
                                lanes)
