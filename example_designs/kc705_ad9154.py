#!/usr/bin/env python3

import argparse

from litex.build.generic_platform import *
from litex.boards.platforms import kc705

from litex.soc.integration.builder import *

from kc705_base import BaseSoC

_jesd204b_io = [
    ("jesd204b_clocks", 0,
        Subsignal("refclk_p", Pins("HPC:GBTCLK0_M2C_P")),
        Subsignal("refclk_n", Pins("HPC:GBTCLK0_M2C_N"))
    ),
    ("jesd204b_sync", 0,
        Subsignal("sync_p", Pins("HPC:LA01_CC_P")),
        Subsignal("sync_n", Pins("HPC:LA01_CC_N")),
        Subsignal("sync2_p", Pins("HPC:LA02_P")),
        Subsignal("sync2_n", Pins("HPC:LA02_N")),
        Subsignal("sysref_p", Pins("HPC:LA00_CC_P")),
        Subsignal("sysref_n", Pins("HPC:LA00_CC_N"))
    ),
    #   FMC lanes / AD9154 lanes
    #         DP0 / SERIND7
    #         DP1 / SERIND6
    #         DP2 / SERIND5
    #         DP3 / SERIND4
    ("jesd204b_data", 0, # AD9154's SERIND7
        Subsignal("txp", Pins("HPC:DP0_C2M_P")),
        Subsignal("txn", Pins("HPC:DP0_C2M_N"))
    ),
    ("jesd204b_data", 1, # AD9154's SERIND6
        Subsignal("txp", Pins("HPC:DP1_C2M_P")),
        Subsignal("txn", Pins("HPC:DP1_C2M_N"))
    ),
    ("jesd204b_data", 2, # AD9154's SERIND5
        Subsignal("txp", Pins("HPC:DP2_C2M_P")),
        Subsignal("txn", Pins("HPC:DP2_C2M_N"))
    ),
    ("jesd204b_data", 3, # AD9154's SERIND4
        Subsignal("txp", Pins("HPC:DP3_C2M_P")),
        Subsignal("txn", Pins("HPC:DP3_C2M_N"))
    ),
    ("jesd204b_spi", 0,
        Subsignal("clk", Pins("HPC:LA03_P")),
        Subsignal("cs_n", Pins("HPC:LA04_N")),
        Subsignal("mosi", Pins("HPC:LA03_N")),
        Subsignal("miso", Pins("HPC:LA04_P"))
    ),
    ("jesd204b_i2c", 0, # KC705 uses an I2C mux
        Subsignal("scl", Pins("")),
        Subsignal("sda", Pins("")),
    ),
]

class Platform(kc705.Platform):
    def __init__(self, *args, **kwargs):
        kc705.Platform.__init__(self, *args, **kwargs)
        self.add_extension(_jesd204b_io)

    def do_finalize(self, fragment):
            self.add_platform_command("""
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 2.5 [current_design]
""")


class AD9154SoC(BaseSoC):
    def __init__(self, platform):
        BaseSoC.__init__(self, platform)


def main():
    platform = Platform()
    soc = AD9154SoC(platform)
    builder = Builder(soc, output_dir="build")
    builder.build()


if __name__ == "__main__":
    main()
