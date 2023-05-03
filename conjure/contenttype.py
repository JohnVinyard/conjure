from enum import Enum

class SupportedContentType(Enum):
    Tensor = 'application/tensor+octet-stream'
    TimeSeries = 'application/time-series+octet-stream'
    TensorMovie = 'application/tensor-movie+octet-stream'
    Audio = 'audio/wav'
    Text = 'text/plain'
