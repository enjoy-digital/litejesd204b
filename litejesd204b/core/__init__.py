from litex.gen import *

from litex.soc.interconnect.csr import *

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
			link = LiteJESD204BLinkTX(phy.data_width, jesd_settings)
			setattr(self.submodules, "link"+str(l), link)
			self.comb += [
				link.sink.valid.eq(transport.source.valid),
				transport.source.ready.eq(link.sink.ready),
				link.sink.data.eq(getattr(transport.source, "data"+str(l))),
				link.source.connect(phy.sink, omit=["frame_last", "multiframe_last"])
			]
