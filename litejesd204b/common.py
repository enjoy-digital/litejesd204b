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
