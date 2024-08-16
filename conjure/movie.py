from matplotlib.animation import FuncAnimation, PillowWriter
import numpy as np
from matplotlib import pyplot as plt
from uuid import uuid4
import os


def tensor_movie(arr: np.ndarray, fps: int=5) -> bytes:
    
    if len(arr.shape) != 3:
        raise ValueError('make_movie expects a 3D array with shape (time, width, height)')

    n_frames, width, height = arr.shape
    
    try:
        filepath = f'/tmp/{uuid4().hex}.gif'

        data = []
        for i in range(n_frames):
            data.append(arr[i])

        fig = plt.figure()
        plot = plt.imshow(data[0])

        def init():
            plot.set_data(data[0])
            return [plot]

        def update(frame):
            plot.set_data(data[frame])
            return [plot]

        frame_delay = int(1000 / fps)
        ani = FuncAnimation(
            fig,
            update,
            frames=np.arange(0, n_frames, 1),
            init_func=init,
            blit=True,
            interval=frame_delay)
        
        ani.save(filepath, writer=PillowWriter(fps=10))
        plt.close()
        
        with open(filepath, 'rb') as f:
            return f.read()
    except Exception as e:
        print(f'Could not write movie due to')
    finally:
        os.remove(filepath)    
    

if __name__ == '__main__':

    data = np.random.binomial(1, 0.1, (128, 128, 128))
    
    with open('movie.gif', 'wb') as f:
        f.write(make_movie(data, fps=5))