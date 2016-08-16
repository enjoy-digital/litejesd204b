# XXX memo

# JESD204B parameters
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

# JESD204B parameters relationship
# JESD204B word size = N’
# F = (M x S x N')/(8 x L)

# XXX memo

# Transport layer

# Data link layer
control_characters = {
    "R": 0b00011100, # K28.0, start of multi-frame
    "A": 0b01111100, # K28.3, Lane alignment
    "Q": 0b10011100, # K28.4, Start of configuration data
    "K": 0b10111100, # K28.5, Group synchronization
    "F": 0b11111100, # K28.7, Frame alignment
}

def data_link_layout(dw):
    layout = [
        ("data", dw),
        ("charisk", dw//8),
    ]
    return EndpointDescription(layout)

configuration_data_length = 13
configuration_data_fields = {
    "DID":       HeaderField(0,  0, 8),
    "BID":       HeaderField(1,  0, 4),
    "ADJCNT":    HeaderField(1,  4, 8),
    "LID":       HeaderField(2,  0, 5),
    "PHADJ":     HeaderField(2,  5, 5),
    "ADJDIR":    HeaderField(2,  6, 6),
    "L":         HeaderField(3,  0, 5),
    "SCR":       HeaderField(3,  5, 8),
    "F":         HeaderField(4,  0, 8),
    "K":         HeaderField(5,  0, 4),
    "M":         HeaderField(6,  0, 8),
    "N":         HeaderField(7,  0, 5),
    "CS":        HeaderField(7,  5, 8),
    "N":         HeaderField(8,  0, 5),
    "SUBCLASS":  HeaderField(8,  5, 8),
    "S":         HeaderField(9,  0, 5),
    "JESDV":     HeaderField(9,  5, 8),
    "CF":        HeaderField(10, 0, 5),
    "HD":        HeaderField(10, 5, 8),
    "RESERVED1": HeaderField(11, 0, 8),
    "RESERVED2": HeaderField(12, 0, 8),
    "FCHK":      HeaderField(13, 0, 8)
}
configuration_data_header = Header(fconfiguration_data_fields,
                                   configuration_data_length,
                                   swap_field_bytes=False)


# Physical layer
