import unittest

from litex.gen import *

from test.model.common import swap_bytes

from litejesd204b.common import *
from litejesd204b.core.link import ILASGenerator

# ilas reference sequence from a validated core
ilas_reference = [
    0x0302011c, 0x07060504, 0x0b0a0908, 0x0f0e0d0c,
    0x13121110, 0x17161514, 0x1b1a1918, 0x1f1e1d1c,
    0x23222120, 0x27262524, 0x2b2a2928, 0x2f2e2d2c,
    0x33323130, 0x37363534, 0x3b3a3938, 0x7c3e3d3c,

    0x0a559c1c, 0x1f010300, 0x202f8d03, 0x61a55a01,
    0x53525150, 0x57565554, 0x5b5a5958, 0x5f5e5d5c,
    0x63626160, 0x67666564, 0x6b6a6968, 0x6f6e6d6c,
    0x73727170, 0x77767574, 0x7b7a7978, 0x7c7e7d7c,

    0x8382811c, 0x87868584, 0x8b8a8988, 0x8f8e8d8c,
    0x93929190, 0x97969594, 0x9b9a9998, 0x9f9e9d9c,
    0xa3a2a1a0, 0xa7a6a5a4, 0xabaaa9a8, 0xafaeadac,
    0xb3b2b1b0, 0xb7b6b5b4, 0xbbbab9b8, 0x7cbebdbc,

    0xc3c2c11c, 0xc7c6c5c4, 0xcbcac9c8, 0xcfcecdcc,
    0xd3d2d1d0, 0xd7d6d5d4, 0xdbdad9d8, 0xdfdedddc,
    0xe3e2e1e0, 0xe7e6e5e4, 0xebeae9e8, 0xefeeedec,
    0xf3f2f1f0, 0xf7f6f5f4, 0xfbfaf9f8 , 0x7cfefdfc]

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
