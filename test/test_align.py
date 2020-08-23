#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litejesd204b.common import *
from litejesd204b.link import Aligner

def aligner_datas_input():
    return [
        0x0302011c, 0x07060504, 0x0b0a0908, 0x0f0e0d0c,
        0x02011c07, 0x0605040b, 0x0a09080f, 0x0e0d0c13,
        0x9c1c1f01, 0x0300202f, 0x8d03a500, 0x00005352,
        0x1c878685, 0x848b8a89, 0x888f8e8d, 0x8c929190,
    ]

def aligner_ctrls_input():
    return [
        0x1, 0x0, 0x0, 0x0,
        0x2, 0x0, 0x0, 0x0,
        0x4, 0x0, 0x0, 0x0,
        0x8, 0x0, 0x0, 0x0,
    ]

def aligner_datas_reference():
    return [
        0x0302011c, 0x07060504, 0x0b0a0908, 0x0f0e0d0c,
        0x0b02011c, 0x0f060504, 0x130a0908, 0x010e0d0c,
        0x202f9c1c, 0xa5000300, 0x53528d03, 0x86850000,
        0x8b8a891c, 0x8f8e8d84, 0x92919088, 0x9291908c,
    ]

def aligner_ctrls_reference():
    return [
        0x1, 0x0, 0x0, 0x0,
        0x1, 0x0, 0x0, 0x0,
        0x1, 0x0, 0x0, 0x0,
        0x1, 0x0, 0x0, 0x0,
    ]

class TestAlign(unittest.TestCase):
    def test_aligner(self):
        dut = Aligner(32)
        dut.errors = 0

        def generator(dut):
            for data, ctrl in zip(aligner_datas_input(), aligner_ctrls_input()):
                yield dut.sink.data.eq(data)
                yield dut.sink.ctrl.eq(ctrl)
                yield

        def checker(dut):
            yield
            yield
            for data, ctrl in zip(aligner_datas_reference(), aligner_ctrls_reference()):
                if (yield dut.source.data) != data:
                    dut.errors += 1
                if (yield dut.source.ctrl) != ctrl:
                    dut.errors += 1
                yield

        run_simulation(dut, [generator(dut), checker(dut)])
        self.assertEqual(dut.errors, 0)

