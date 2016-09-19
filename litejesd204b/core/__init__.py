from litex.gen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litejesd204b.common import *
from litejesd204b.core.transport import LiteJESD204BTransportTX
from litejesd204b.core.link import LiteJESD204BLinkTX


class LiteJESD204BCoreTX(Module, AutoCSR):
    def __init__(self, phys, jesd_settings, converter_data_width):
        # transport
        transport = LiteJESD204BTransportTX(jesd_settings.transport,
                                            jesd_settings.phy,
                                            converter_data_width)
        self.submodules += transport

        # link
        for l, phy in enumerate(phys):
            jesd_settings.phy.lid = l
            cdc = stream.AsyncFIFO([("data", phy.data_width)], 8)
            ClockDomainsRenamer({"write": "sys", "read": "jesd_phy"+str(l)+"_tx"})(cdc) # FIXME
            self.submodules += cdc
            link = LiteJESD204BLinkTX(phy.data_width, jesd_settings)
            link = ClockDomainsRenamer({"link_tx": "jesd_phy"+str(l)+"_tx"})(link) # FIXME
            setattr(self.submodules, "link"+str(l), link)

            self.comb += [
                cdc.sink.valid.eq(transport.source.valid),
                transport.source.ready.eq(cdc.sink.ready),
                cdc.sink.data.eq(getattr(transport.source, "data"+str(l))),
                cdc.source.connect(link.sink),
                link.source.connect(phy.sink, omit=["frame_last", "multiframe_last"])
            ]
