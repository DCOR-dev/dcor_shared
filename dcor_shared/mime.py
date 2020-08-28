#: Maps formats to file extensions
DC_MIME_TYPES = {
    "RT-DC": ".rtdc",
    "DC": ".dc",  # more general
}

#: Valid values for resource "format"
VALID_FORMATS = sorted(DC_MIME_TYPES.keys()) + ["RT-FDC"]
