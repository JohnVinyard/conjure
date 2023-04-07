import falcon
from http import HTTPStatus
from conjure.decorate import Conjure
import multiprocessing
import gunicorn.app.base
import sys


class RootResource(object):

    def __init__(self, conjure: Conjure):
        super().__init__()
        self.conjure = conjure

    def on_get(self, req: falcon.Request, res: falcon.Response):
        # TODO: Paging
        keys = list(k.decode() for k in self.conjure.iter_keys())
        res.media = keys
        res.status = falcon.HTTP_OK


class Resource(object):
    def __init__(self, conjure: Conjure):
        super().__init__()
        self.conjure = conjure

    def on_get(self, req: falcon.Request, res: falcon.Response, key: str):
        try:
            result = self.conjure.get_raw(key)
            res.content_length = result.content_length
            res.content_type = result.content_type
            res.body = result.raw
            res.status = falcon.HTTP_OK
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND


class Application(falcon.API):

    def __init__(self, conjure: Conjure):
        super().__init__(middleware=[])
        self.conjure = conjure
        self.add_route('/', RootResource(conjure))
        self.add_route('/{key}', Resource(conjure))


def handler_app(environ, start_response):
    response_body = b'Works fine'
    status = '200 OK'

    response_headers = [
        ('Content-Type', 'text/plain'),
    ]

    start_response(status, response_headers)

    return [response_body]


class StandaloneApplication(gunicorn.app.base.BaseApplication):

    def __init__(self, app, **options):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items()
                  if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1


def serve_conjure(
        conjure: Conjure,
        port: int = 8888,
        n_workers: int = None,
        revive=True):

    app = Application(conjure)

    def worker_int(worker):
        print('SIGNAL', worker, revive)
        if not revive:
            print('Exit because of worker failure')
            sys.exit(1)

    def run():
        standalone = StandaloneApplication(
            app,
            bind=f'0.0.0.0:{port}',
            workers=n_workers or number_of_workers(),
            worker_int=worker_int)
        standalone.run()

    p = multiprocessing.Process(target=run, args=())
    p.start()
    return p
