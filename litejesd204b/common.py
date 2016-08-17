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

# AD9154 parameters:
# CF always 0 for ADI devices
# K=16 or 32
# control bits not supported
# M=4
# L=4 with KC705/L=8 with KU105
# if F=1, HD must be set to 1
# S=1
# F=2

# XXX memo

# Transport layer

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
    "did":       Field(0,  0, 8),
    #----------- octet 1 --------------
    "bid":       Field(1,  0, 4),
    "adjcnt":    Field(1,  4, 8),
    #----------- octet 2 --------------
    "lid":       Field(2,  0, 5),
    "phadj":     Field(2,  5, 5),
    "adjdir":    Field(2,  6, 6),
    #----------- octet 3 --------------
    "l":         Field(3,  0, 5),
    "scr":       Field(3,  7, 8),
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
    "subclassv": Field(8,  5, 8),
    #----------- octet 9 --------------
    "s":         Field(9,  0, 5),
    "jesdv":     Field(9,  5, 8),
    #----------- octet 10 -------------
    "cf":        Field(10, 0, 5),
    "hd":        Field(10, 5, 8),
    #----------- octet 11 -------------
    "res1":      Field(11, 0, 8),
    #----------- octet 12 -------------
    "res2":      Field(12, 0, 8),
    #----------- octet 13 -------------
    "fchk":      Field(13, 0, 8)
}

class LiteJESD204ConfigurationData:
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
