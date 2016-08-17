from litejesd204b.common import *

config = LiteJESD204ConfigurationData()
config.did = 2
config.bid = 4
config.lid = 8
print(config.get_octets())
print("{:02x}".format(config.get_checksum()))
