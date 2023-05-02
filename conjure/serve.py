from typing import List, Union
from urllib.parse import ParseResult, urlparse
import falcon
from conjure.decorate import Conjure, Index
import multiprocessing
import gunicorn.app.base
import sys
import os
from collections import defaultdict

from conjure.storage import ensure_bytes, ensure_str

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


class ListFunctions(object):
    """
    List all functions served by this server instance
    """

    def __init__(self, functions: List[Conjure]):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}

    def on_get(self, req: falcon.Request, res: falcon.Response):
        res.media = list(map(
            lambda x: {
                'id': x.identifier,
                'name': x.name,
                'description': x.description or '',
                'content_type': x.content_type,
                'code': x.code,
                'url': f'/functions/{x.identifier}',
                'feed': f'/feed/{x.identifier}',
                'meta': x.most_recent_meta().conjure_data
            }, self.functions.values()))
        res.status = falcon.HTTP_OK


class Function(object):
    def __init__(self, functions: List[Conjure], indexes: List[Index] = []):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}
        # organize indexes
        grouped_indexes: dict[List[Index]] = defaultdict(list)
        for index in indexes:
            grouped_indexes[index.conjure_identifier].append(index)

        self.grouped = grouped_indexes

    def on_get(self, req: falcon.Request, res: falcon.Response, identifier: str):
        try:
            func = self.functions[identifier]
            res.media = {
                'id': func.identifier,
                'name': func.name,
                'description': func.description or '',
                'code': func.code,
                'url': f'/functions/{func.identifier}',
                'feed': f'/feed/{func.identifier}',
                'keys': list(k.decode() for k in func.iter_keys())[:10],
                'indexes': list(map(lambda x: x.name, self.grouped.get(identifier, [])))
            }
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND


class FunctionIndex(object):
    def __init__(self, functions: List[Conjure], indexes: List[Index]):
        super().__init__()

        # organize indexes
        grouped_indexes: dict[List[Index]] = defaultdict(list)
        for index in indexes:
            grouped_indexes[index.conjure_identifier].append(index)

        self.grouped = grouped_indexes

    def on_get(
            self,
            req: falcon.Request,
            res: falcon.Response,
            identifier: str,
            index_name: str):

        try:
            candidates = self.grouped[identifier]
            filtered_candidates = list(filter(lambda x: x.name == index_name, candidates))
            candidate: Index = filtered_candidates[0]
            query = req.params['q']
            results = candidate.search(query)
            res.media = results
        except (KeyError, IndexError) as e:
            res.status = falcon.HTTP_NOT_FOUND


class FunctionResult(object):
    def __init__(self, functions: List[Conjure]):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}

    def on_get(self, req: falcon.Request, res: falcon.Response, identifier: str, key: str):
        try:
            func = self.functions[identifier]
            result = func.get_raw(key)
            res.content_length = result.content_length
            res.content_type = result.content_type
            res.body = result.raw
            res.status = falcon.HTTP_OK
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND


class FunctionFeed(object):
    def __init__(self, functions: List[Conjure]):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}
        print(list(self.functions.keys()))

    def on_get(self, req: falcon.Request, res: falcon.Response, identifier: str):
        try:
            func = self.functions[identifier]
            offset = req.get_param('offset')
            items = list(func.feed(offset))  # [{ timestamp, key }]
            res.media = list(
                map(lambda x: {key: value.decode() for key, value in x.items()}, items))
            res.status = falcon.HTTP_OK
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND


class Dashboard(object):

    def __init__(self, conjure_funcs: List[Conjure], port: int = None):
        super().__init__()
        self.conjure_funcs = {f.identifier: f for f in conjure_funcs}
        self.port = port

    def _uri(self, conj: Conjure, key: Union[str, bytes]) -> ParseResult:
        # TODO: host should not be hard coded here
        return urlparse(f'http://localhost:{self.port}/functions/{conj.identifier}/{ensure_str(key)}')

    def _item_html(self, conjure: Conjure) -> str:
        meta = conjure.most_recent_meta()

        if not meta.public_uri:
            meta = meta.with_public_uri(self._uri(conjure, meta.key))

        html = meta.conjure_html()

        return html

    def on_get(self, req: falcon.Request, res: falcon.Response, function_id=None):

        with open(os.path.join(MODULE_DIR, 'style.css'), 'r') as f:
            style = f.read()

        with open(os.path.join(MODULE_DIR, 'imports.json'), 'r') as f:
            imports = f.read()

        with open(os.path.join(MODULE_DIR, 'dashboard.mjs'), 'r') as f:
            script = f.read()

        with open(os.path.join(MODULE_DIR, 'dashboard.html'), 'r') as f:
            content = f.read()
            res.content_length = len(content)
            res.body = content.format(
                script=script,
                imports=imports,
                style=style)
            res.set_header('content-type', 'text/html')
            res.status = falcon.HTTP_OK


class MutliFunctionApplication(falcon.API):

    def __init__(
            self,
            conjure_funcs: List[Conjure],
            indexes: List[Index] = [],
            port: int = None):

        super().__init__(middleware=[])
        self.functions = conjure_funcs
        self.port = port

        self.add_route('/functions', ListFunctions(conjure_funcs))

        self.add_route('/functions/{identifier}', Function(conjure_funcs, indexes))

        self.add_route(
            '/functions/{identifier}/indexes/{index_name}', 
            FunctionIndex(conjure_funcs, indexes))

        self.add_route('/feed/{identifier}', FunctionFeed(conjure_funcs))
        self.add_route('/functions/{identifier}/{key}',
                       FunctionResult(conjure_funcs))
        self.add_route('/dashboard', Dashboard(conjure_funcs, port=port))
        self.add_route(
            '/dashboard/functions/{function_id}', Dashboard(conjure_funcs, port=port))


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


def serve_conjure(
        conjure_funcs: List[Conjure],
        port: int = 8888,
        n_workers: int = None,
        revive=True,
        indexes: List[Index] = []):

    app = MutliFunctionApplication(conjure_funcs, indexes=indexes, port=port)

    def worker_int(worker):
        if not revive:
            print('Exit because of worker failure')
            sys.exit(1)

    worker_count = (multiprocessing.cpu_count() * 2) + 1

    def run():
        standalone = StandaloneApplication(
            app,
            bind=f'0.0.0.0:{port}',
            workers=n_workers or worker_count,
            worker_int=worker_int)
        standalone.run()

    p = multiprocessing.Process(target=run, args=())
    p.start()
    return p
