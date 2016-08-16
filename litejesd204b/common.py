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

# Physical layer
