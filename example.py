import numpy as np
from conjure import serve_conjure
from conjure.decorate import numpy_conjure, time_series_conjure
from conjure.storage import LmdbCollection
from time import sleep
from threading import Thread

collection = LmdbCollection('http_test')


@numpy_conjure(collection)
def spectral_magnitude(arr: np.ndarray):
    spec = np.fft.rfft(arr, axis=-1, norm='ortho')
    spec = np.abs(spec).astype(np.float32)
    return spec


# @audio_conjure(collection)
# def resample_audio(url):
#     import requests
#     from io import BytesIO
#     import zounds
#     from librosa import resample

#     resp = requests.get(url)
#     bio = BytesIO(resp.content)
#     original_audio = zounds.AudioSamples.from_file(bio).mono
#     target_sr = zounds.SR11025()
#     samples = resample(
#         original_audio,
#         orig_sr=int(original_audio.samplerate),
#         target_sr=int(target_sr))
#     samples = zounds.AudioSamples(samples, target_sr)

#     n_samples = 2 ** 15
#     resampled = zounds.AudioSamples(samples[:n_samples], target_sr)

#     output = BytesIO()
#     resampled.encode(output)
#     output.seek(0)
#     return output.read()


d = {
    'values': np.random.uniform(0, 1, (2, 100)).astype(np.float32)
}


@time_series_conjure(collection, 'loss')
def time_series():
    d['values'] = np.concatenate(
        [d['values'], np.random.uniform(0, 1, (2, 2)).astype(np.float32)], axis=-1)
    return d['values']


def add_values():
    while True:
        try:
            time_series()
            sleep(5)
        except KeyboardInterrupt:
            return


if __name__ == '__main__':
    a = np.random.normal(0, 1, 10)
    b = np.random.normal(0, 1, (10, 10))
    c = np.random.normal(0, 1, (10, 10, 10))

    t = Thread(target=add_values)
    t.start()

    # audio = resample_audio('https://music-net.s3.amazonaws.com/1919')

    time_series()

    try:
        spectral_magnitude(a)
        spectral_magnitude(b)
        spectral_magnitude(c)

        p = serve_conjure(
            [
                # resample_audio,
                time_series,
                spectral_magnitude
            ],
            port=9999,
            n_workers=2)

        input('waiting...')
        p.kill()
    finally:
        time_series.storage.destroy()
        pass
