# XXX memo

# JESD204B parameters:
# L:    Number of lanes per converter device, 1-8
# M:    Number of converters per device, 1-256
# F:    Number of octets per frame, 1, 2, 4-256
# S:    Number of transmitted samples per converter per frame, 1-32
# N:    Number of conversion bits per converter, 1-32
# N':   Number of transmitted bits per sample, 1-32
# K:    Number of frames per multiframe, 17/F ≤ K ≤ 32 ; 1-32
# CS:   Number of control bits per conversion sample, 0-3
# CF:   Number of control words per frame clock period per link, 0-32
# HD:   High Density user data format,0 or 1
# LMFC: Local multiframe clock, (F × K /4) link clock counts

# JESD204B parameters relationship:
# JESD204B word size = N’
# F = (M x S x N')/(8 x L)

# SC: Converter sample clock
# FC: Frame clock
# LR: Line Rate
# LMFC: Local multi-frame clock

# FC = SC/S
# LMFC = FC/K
# LR = (M x S x N' x 10/8 x FC)/L

# AD9154 parameters:
# CF always 0 for ADI devices
# K = 16 or 32
# control bits not supported
# M = 4
# L = 4 with KC705/L=8 with KU105
# if F = 1, HD must be set to 1
# S = 1
# F = 2

# XXX memo

# Transport layer

class LiteJESD204BTransportSettings:
    def __init__(self, f, s, k, cs):
        self.f = f
        self.s = s
        self.k = k
        self.cs = cs


# Link layer
control_characters = {
    "R": 0b00011100, # K28.0, start of multi-frame
    "A": 0b01111100, # K28.3, Lane alignment
    "Q": 0b10011100, # K28.4, Start of configuration data
    "K": 0b10111100, # K28.5, Group synchronization
    "F": 0b11111100, # K28.7, Frame alignment
}

def link_layout(dw):
    layout = [
        ("data", dw),
        ("charisk", dw//8),
        ("frame_last", 1),
        ("multiframe_last", 1),
        ("scrambled", 1)
    ]
    return EndpointDescription(layout)

class Field:
    def __init__(self, octet, offset, width):
        self.octet = octet
        self.offset = offset
        self.width = width


configuration_data_length = 14
configuration_data_fields = {
    #----------- octet 0 --------------
    "did":       Field(0,  0, 8), # device id
    #----------- octet 1 --------------
    "bid":       Field(1,  0, 4), # bank id
    "adjcnt":    Field(1,  4, 8), # N/A (subclass 2 only)
    #----------- octet 2 --------------
    "lid":       Field(2,  0, 5), # lane id
    "phadj":     Field(2,  5, 5), # N/A (subclass 2 only)
    "adjdir":    Field(2,  6, 6), # N/A (subclass 2 only)
    #----------- octet 3 --------------
    "l":         Field(3,  0, 5),
    "scr":       Field(3,  7, 8), # scrambling enable
    #----------- octet 4 --------------
    "f":         Field(4,  0, 8),
    #----------- octet 5 --------------
    "k":         Field(5,  0, 4),
    #----------- octet 6 --------------
    "m":         Field(6,  0, 8),
    #----------- octet 7 --------------
    "n":         Field(7,  0, 5),
    "cs":        Field(7,  6, 8),
    #----------- octet 8 --------------
    "n":         Field(8,  0, 5),
    "subclassv": Field(8,  5, 8), # device subclass version
    #----------- octet 9 --------------
    "s":         Field(9,  0, 5),
    "jesdv":     Field(9,  5, 8), # jsed204 version
    #----------- octet 10 -------------
    "cf":        Field(10, 0, 5),
    "hd":        Field(10, 5, 8),
    #----------- octet 11 -------------
    "res1":      Field(11, 0, 8),
    #----------- octet 12 -------------
    "res2":      Field(12, 0, 8),
    #----------- octet 13 -------------
    "chksum":    Field(13, 0, 8)
}


class LiteJESD204BConfigurationData:
    def __init__(self):
        for k in configuration_data_fields.keys():
            setattr(self, k, 0)

    def get_octets(self):
        octets = [0]*configuration_data_length
        for name, field in configuration_data_fields.items():
            octets[field.octet] |= ((getattr(self, name) << field.offset) &
                                    2**(field.width-field.offset)-1)
        return octets

    def get_checksum(self):
        checksum = 0
        for octet in self.get_octets()[:-1]:
                checksum = (checksum + octet) % 256
        return checksum

# Physical layer

class LiteJESD204BPhysicalSettings:
    def __init__(self, l, m, n, np, sc):
        self.l = l
        self.m = m
        self.n = n
        self.np = np
        self.sc = sc

        # only support subclass 1
        self.subclassv = 0b001
        self.adjcnt = 0
        self.adjdir = 0
        self.phadj = 0

        # jsed204b revision
        self.jsedv = 0b001


# Global

class LiteJESD204BSettings:
    def __init__(self,
        phy_settings,
        transport_settings,
        did, bid):
        self.phy_settings = phy_settings
        self.transport_settings = transport_settings
        self.did = did
        self.bid = bid

    def get_configuration_data(self):
        cd = LiteJESD204BConfigurationData()
        for k in configuration_data_fields.keys():
            for settings in [self.phy_settings,
                             self.transport_settings]:
                try:
                    setattr(cd, k, getattr(settings, k))
                except:
                    pass
        cd.did = self.did
        cd.bid = self.bid

        octets = cd.get_octets()
        chksum = cd.get_checksum()
        return octets[:-1] + [chksum]

    def get_clocks(self):
        ts = self.transport_settings
        ps = self.phy_settings

        fc = ps.sc/ts.s
        lmfc = fc/ts.k

        lr = (ps.m*ts.s*ps.np*10/8*fc)/ps.l

        return ps.sc, fc, lmfc, lr
