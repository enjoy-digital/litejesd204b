#!/usr/bin/env python3

import time

from litex.soc.tools.remote.comm_udp import CommUDP
from libbase.ad9154_spi import AD9154SPI

wb = CommUDP("192.168.1.50", 1234, csr_data_width=32, debug=False)
wb.open()

# # #

ident = ""
for i in range(1, 64):
	ident += chr(wb.read(0xe0001800 + 4*i))
print(ident)

ad9154_spi = AD9154SPI(wb.regs)
for i in range(16):
	print(ad9154_spi.read(i))

# # #

wb.close()
