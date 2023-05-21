import re
import numpy as np
import requests
from conjure.contenttype import SupportedContentType
from conjure.decorate import audio_conjure, conjure_index, numpy_conjure, text_conjure, time_series_conjure
from conjure.serve import serve_conjure
from conjure.storage import LmdbCollection, LocalCollectionWithBackup, ensure_str
from time import sleep
from threading import Thread
from random import random
import torch
import zounds
from io import BytesIO
import zounds

# collection = LmdbCollection('conjure-test')
collection = LocalCollectionWithBackup(
    local_path='conjure-test',
    remote_bucket='conjure-test',
    is_public=True,
    local_backup=False,
    cors_enabled=True
)


@audio_conjure(collection)
def musicnet_segment(url):
    import requests
    from io import BytesIO
    import zounds
    from librosa import resample

    resp = requests.get(url)
    bio = BytesIO(resp.content)
    original_audio = zounds.AudioSamples.from_file(bio).mono
    target_sr = zounds.SR11025()
    samples = resample(
        original_audio,
        orig_sr=int(original_audio.samplerate),
        target_sr=int(target_sr))
    samples = zounds.AudioSamples(samples, target_sr)

    n_samples = 2 ** 15
    resampled = zounds.AudioSamples(samples[:n_samples], target_sr)

    output = BytesIO()
    resampled.encode(output)
    output.seek(0)
    return output.read()

@numpy_conjure(collection)
def musicnet_spectrogram(url):
    import zounds
    from io import BytesIO
    audio = musicnet_segment(url)
    input = BytesIO(audio)
    input.seek(0)
    samples = zounds.AudioSamples.from_file(input)
    spec = np.abs(zounds.spectral.stft(samples))
    spec = np.log(1 + spec)
    spec += spec.min()
    spec /= (spec.max() + 1e-12)
    return spec.astype(np.float32)


@numpy_conjure(collection, content_type=SupportedContentType.TensorMovie.value)
def scattering_like_transform(arr: np.ndarray):
    signal = torch.from_numpy(arr).float().view(1, 1, arr.shape[-1])
    sr = zounds.SR22050()
    band = zounds.FrequencyBand(20, sr.nyquist)

    channels = 128

    scale = zounds.MelScale(band, channels)
    fb = zounds.learn.FilterBank(
        sr, 256, scale, 0.1, normalize_filters=True, a_weighting=False)
    spec = fb.forward(signal, normalize=False)

    window_size = 512
    step_size = window_size // 2
    n_coeffs = window_size // 2 + 1

    windowed = spec.unfold(-1, window_size, step_size)

    scatter = torch.abs(torch.fft.rfft(windowed, dim=-1, norm='ortho'))
    scatter = torch.log(1 + scatter)
    scatter += scatter.min()

    result = scatter.view(channels, -1, n_coeffs).permute(1, 2, 0).float()

    data = result.data.cpu().numpy()
    data = data / (np.abs(data.max()) + 1e-12)  # normalize

    return data.astype(np.float32)

# @numpy_conjure(collection)
# def spectral_magnitude(arr: np.ndarray):
#     """
#     Compute the spectral magnitude along the last dimension of
#     an arbitrarily-sized tensor
#     """
#     spec = np.fft.rfft(arr, axis=-1, norm='ortho')
#     spec = np.abs(spec).astype(np.float32)
#     return spec


# d = {
#     'values': np.random.uniform(0, 1, (2, 100)).astype(np.float32)
# }


# @time_series_conjure(collection, 'loss')
# def time_series():
#     """
#     Append values to a time series
#     """
#     d['values'] = np.concatenate(
#         [d['values'], np.random.uniform(0, 1, (2, 2)).astype(np.float32)], axis=-1)
#     return d['values']


# def add_values():
#     while True:
#         print('add_values')
#         try:
#             time_series()
#             sleep(random() * 10)
#         except KeyboardInterrupt:
#             return


# def compute_new_spectral_magnitude():
#     while True:
#         print('compute_new_spectral_magnitude')
#         try:
#             inp = np.random.normal(0, 1, (10, 10, 10))
#             spectral_magnitude(inp)
#             sleep(random() * 10)
#         except KeyboardInterrupt:
#             return


# def get_all_links():
#     hostname = 'http://textfiles.com'
#     resp = requests.get(f'{hostname}/games/')
#     pattern = re.compile(r'HREF="(?P<path>[^"]+\.txt)"')
#     for match in pattern.finditer(resp.content.decode()):
#         yield f'{hostname}/games/{match.groupdict()["path"]}'

# all_links = list(get_all_links())


# @text_conjure(collection)
# def textfile(url):
#     """

#     #Textfile

#     Download a text document from [textfiles.com](http://textfiles.com/games/)

#     """
#     resp = requests.get(url)
#     return resp.content

# @conjure_index(textfile, collection.index_storage('content_index'))
# def content_index(key: bytes, result: str, *args, **kwargs):
#     """

#     #Word-Based Index

#     Produce a...

#     ```
#     word -> [doc1, doc2]
#     ```

#     ...to document mapping

#     """
#     words = result.split()
#     for word in words:
#         yield word.lower(), dict(key=ensure_str(key), word_count=len(words))


# def fetch_data():
#     while all_links:
#         try:
#             n = all_links.pop()
#             print(f'fetching {n}')
#             textfile(n)
#         except:
#             continue
if __name__ == '__main__':

    try:
        # fetch_data()
        # print('indexing...')
        # content_index.index()

        url = 'https://music-net.s3.amazonaws.com/1919'

        result = musicnet_segment(url)
        io = BytesIO(result)
        samples = zounds.AudioSamples.from_file(io)

        spec = musicnet_spectrogram(url)
        aim = scattering_like_transform(samples)

        p = serve_conjure(
            [
                musicnet_segment,
                musicnet_spectrogram,
                scattering_like_transform
            ],
            indexes=[
                # content_index
            ],
            port=9999,
            n_workers=2)

        input('waiting...')
        p.kill()
    finally:
        # musicnet_segment.storage.destroy()
        pass
