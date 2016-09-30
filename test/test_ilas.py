import unittest

from litex.gen import *

from test.model.common import swap_bytes

from litejesd204b.common import *
from litejesd204b.core.link import ILASGenerator

# ilas reference sequence from a validated core
ilas_reference = [
    0x1c010203, 0x04050607, 0x08090a0b, 0x0c0d0e0f,
    0x10111213, 0x14151617, 0x18191a1b, 0x1c1d1e1f,
    0x20212223, 0x24252627, 0x28292a2b, 0x2c2d2e2f,
    0x30313233, 0x34353637, 0x38393a3b, 0x3c3d3e7c,

    0x1c9c550a, 0x0003011f, 0x038d2f20, 0x015aa561,
    0x50515253, 0x54555657, 0x58595a5b, 0x5c5d5e5f,
    0x60616263, 0x64656667, 0x68696a6b, 0x6c6d6e6f,
    0x70717273, 0x74757677, 0x78797a7b, 0x7c7d7e7c,

    0x1c818283, 0x84858687, 0x88898a8b, 0x8c8d8e8f,
    0x90919293, 0x94959697, 0x98999a9b, 0x9c9d9e9f,
    0xa0a1a2a3, 0xa4a5a6a7, 0xa8a9aaab, 0xacadaeaf,
    0xb0b1b2b3, 0xb4b5b6b7, 0xb8b9babb, 0xbcbdbe7c,

    0x1cc1c2c3, 0xc4c5c6c7, 0xc8c9cacb, 0xcccdcecf,
    0xd0d1d2d3, 0xd4d5d6d7, 0xd8d9dadb, 0xdcdddedf,
    0xe0e1e2e3, 0xe4e5e6e7, 0xe8e9eaeb, 0xecedeeef,
    0xf0f1f2f3, 0xf4f5f6f7, 0xf8f9fafb, 0xfcfdfe7c]

class TestILAS(unittest.TestCase):
    def test_ilas(self):
        ps = JESD204BPhysicalSettings(l=4, m=4, n=14, np=16, sc=1*1e9)
        ts = JESD204BTransportSettings(f=2, s=1, k=32, cs=2)
        jesd_settings = JESD204BSettings(ps, ts, did=0x55, bid=0xa)

        ilas = ILASGenerator(32, 2, 32, jesd_settings.get_configuration_data())

        ilas_output = []

        def generator(dut):
            yield dut.source.ready.eq(1)
            for i in range(128):
                if (yield dut.source.valid) and (yield dut.source.ready):
                    ilas_output.append((yield dut.source.data))
                yield

        run_simulation(ilas, generator(ilas), vcd_name="sim.vcd")
        self.assertEqual(ilas_reference, ilas_output)
