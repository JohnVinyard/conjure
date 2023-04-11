import numpy as np
from conjure import serve_conjure
from conjure.decorate import audio_conjure, numpy_conjure
from conjure.storage import LmdbCollection


collection = LmdbCollection('http_test')


# @numpy_conjure(collection)
# def spectral_magnitude(arr: np.ndarray):
#     spec = np.fft.rfft(arr, axis=-1, norm='ortho')
#     spec = np.abs(spec).astype(np.float32)
#     return spec


@audio_conjure(collection)
def resample_audio(url):
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


if __name__ == '__main__':
    # a = np.random.normal(0, 1, 10)
    # b = np.random.normal(0, 1, (10, 10))
    # c = np.random.normal(0, 1, (10, 10, 10))

    a = resample_audio('https://music-net.s3.amazonaws.com/1919')

    try:
        # spectral_magnitude(a)
        # spectral_magnitude(b)
        # spectral_magnitude(c)

        p = serve_conjure(resample_audio, port=9999, n_workers=2)

        input('waiting...')
        p.kill()
    finally:
        # resample_audio.storage.destroy()
        pass
