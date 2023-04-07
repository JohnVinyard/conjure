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
        # res.status = HTTPStatus.OK 



class Application(falcon.API):

    def __init__(self, conjure: Conjure):
        super().__init__(middleware=[])
        self.conjure = conjure

    # self.resp_options.media_handlers = falcon.media.Handlers({
    #     'application/json': JSONHandler(app_entity_links),
    # })
    # self.add_route('/', RootResource(
    #     users_repo, sounds_repo, annotations_repo, is_dev_environment))
    # self.add_route('/users', UsersResource(email_whitelist))
    # self.add_route(USER_URI_TEMPLATE, UserResource())
    # self.add_route('/sounds', SoundsResource())
    # self.add_route(SOUND_URI_TEMPLATE, SoundResource())
    # self.add_route(
    #     '/sounds/{sound_id}/annotations', SoundAnnotationsResource())
    # self.add_route('/users/{user_id}/sounds', UserSoundsResource())
    # self.add_route('/users/{user_id}/annotations',
    #                UserAnnotationResource())
    # self.add_route('/annotations', AnnotationsResource())

    # self.add_error_handler(PermissionsError, permissions_error)
    # self.add_error_handler(
    #     CompositeValidationError, composite_validation_error)
    # self.add_error_handler(EntityNotFoundError, not_found_error)

        self.add_route('/', RootResource(conjure))

    # def add_route(self, route, resource, *args, **kwargs):
    #     self._doc_routes.append((route, resource))
    #     super().add_route(route, resource, *args, **kwargs)




def number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1


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
    
def serve_conjure(conjure: Conjure, port: int = 8888, n_workers: int = None, revive=True):

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