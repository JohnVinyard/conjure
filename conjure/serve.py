from typing import List, Union
from urllib.parse import ParseResult, urlparse
import falcon
from conjure.decorate import Conjure
from conjure.indexes import ConjureIndex, TextIndex
import multiprocessing
import gunicorn.app.base
import sys
import os
from markdown import markdown

from conjure.storage import ensure_str

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


def uri(port: int, conj: Conjure, key: Union[str, bytes]) -> ParseResult:
    # TODO: host should not be hard coded here
    return urlparse(f'http://localhost:{port}/functions/{conj.identifier}/{ensure_str(key)}')

    
class ListFunctions(object):
    """
    List all functions served by this server instance
    """

    def __init__(self, functions: List[Conjure], port: int):
        super().__init__()

        self.functions = {f.identifier: f for f in functions}
        self.port = port

    def on_get(self, req: falcon.Request, res: falcon.Response):
        funcs = self.functions.values()
        results = []

        for x in funcs:
            meta = x.most_recent_meta()
            if meta is None:
                # no results yet, but the feed can still be watched for the
                # first one
                meta_data = {
                    'key': None,
                    'public_uri': None,
                    'content_type': x.content_type,
                    'feed_uri': f'/feed/{ensure_str(x.identifier)}',
                    'func_name': ensure_str(x.name),
                    'func_identifier': ensure_str(x.identifier),
                }
            else:
                meta_data = meta.with_public_uri(uri(self.port, x, meta.key)).conjure_data

            # a stable URL for whichever result is newest
            meta_data['latest_uri'] = f'/functions/{ensure_str(x.identifier)}/latest'

            results.append({
                'id': x.identifier,
                'name': x.name,
                'description': x.description or '',
                'content_type': x.content_type,
                'code': x.code,
                'url': f'/functions/{x.identifier}',
                'feed': f'/feed/{x.identifier}',
                'meta': meta_data
            })
        res.media = results
        res.status = falcon.HTTP_OK


def index_summary(func: Conjure, index: ConjureIndex) -> dict:
    description = '\n'.join(
        line.strip() for line in (index.extract.__doc__ or '').split('\n'))
    return {
        'name': index.name,
        'type': index.kind,
        'description': markdown(description),
        # only text indices can be searched with a query string
        'search': f'/functions/{func.identifier}/indexes/{index.name}?q='
            if isinstance(index, TextIndex) else None,
    }


class Function(object):
    def __init__(self, functions: List[Conjure]):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}

    def on_get(self, req: falcon.Request, res: falcon.Response, identifier: str):
        try:
            func = self.functions[identifier]
            res.media = {
                'id': func.identifier,
                'name': func.name,
                'description': func.description_html,
                'code': func.code,
                'url': f'/functions/{func.identifier}',
                'feed': f'/feed/{func.identifier}',
                # newest first
                'keys': [ensure_str(k) for k in func.recent_keys(limit=10)],
                # the dashboard doesn't yet support indices
                'indexes': [],
                'indices': [index_summary(func, index) for index in func.indices],
            }
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND


class FunctionIndex(object):
    """
    Search one of a function's text indices with a query string, e.g.
    /functions/{identifier}/indexes/{index_name}?q=some+words&limit=10
    """

    DEFAULT_LIMIT = 25

    def __init__(self, functions: List[Conjure]):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}

    def on_get(
            self,
            req: falcon.Request,
            res: falcon.Response,
            identifier: str,
            index_name: str):

        try:
            func = self.functions[identifier]
            index = func.indices[index_name]
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND
            return

        if not isinstance(index, TextIndex):
            res.status = falcon.HTTP_BAD_REQUEST
            res.media = {
                'error': f'{index.kind} indices cannot be searched with a query string'}
            return

        query = req.get_param('q') or ''
        limit = req.get_param_as_int('limit', min_value=1) or self.DEFAULT_LIMIT

        hits = index.search(query, limit=limit)
        res.media = [
            {
                'key': ensure_str(hit.key),
                'score': hit.score,
                'url': f'/functions/{func.identifier}/{ensure_str(hit.key)}',
            }
            for hit in hits
        ]


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
            res.text = result.raw
            res.status = falcon.HTTP_OK
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND


class LatestFunctionResult(object):
    """
    The most recently stored result for a function, i.e. a shortcut for
    reading the function's feed, and then requesting its last key.  Responds
    with 404 if the function has no results yet.

    The key that was served is in the X-Conjure-Key header, and is also the
    ETag, so clients can poll cheaply, either with HEAD requests, or with
    conditional GET requests, which return 304 Not Modified until a newer
    result is stored.
    """

    KEY_HEADER = 'X-Conjure-Key'

    def __init__(self, functions: List[Conjure]):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}

    def _latest(self, res: falcon.Response, identifier: str):
        """
        Set headers describing the latest result, and return its function
        and key, or set a 404 status and return None
        """
        # the latest result changes over time, so caches must always revalidate
        res.cache_control = ['no-cache']

        func = self.functions.get(identifier)
        key = None if func is None else func.most_recent_key()
        if key is None:
            res.status = falcon.HTTP_NOT_FOUND
            return None

        key = ensure_str(key)
        res.set_header(self.KEY_HEADER, key)
        res.etag = key
        return func, key

    def on_head(self, req: falcon.Request, res: falcon.Response, identifier: str):
        self._latest(res, identifier)

    def on_get(self, req: falcon.Request, res: falcon.Response, identifier: str):
        latest = self._latest(res, identifier)
        if latest is None:
            return
        func, key = latest

        if req.if_none_match and any(
                etag == '*' or etag == key for etag in req.if_none_match):
            res.status = falcon.HTTP_NOT_MODIFIED
            return

        try:
            result = func.get_raw(key)
        except KeyError:
            # the result was deleted after the feed was read
            res.status = falcon.HTTP_NOT_FOUND
            return

        res.content_length = result.content_length
        res.content_type = result.content_type
        res.text = result.raw
        res.status = falcon.HTTP_OK


class FunctionFeed(object):
    def __init__(self, functions: List[Conjure]):
        super().__init__()
        self.functions = {f.identifier: f for f in functions}
        print(list(self.functions.keys()))

    def on_get(self, req: falcon.Request, res: falcon.Response, identifier: str):
        try:
            func = self.functions[identifier]
        except KeyError:
            res.status = falcon.HTTP_NOT_FOUND
            return

        # a missing or empty offset means "from the start of the feed"
        offset = req.get_param('offset') or None

        try:
            items = list(func.feed(offset))  # [{ timestamp, key }]
        except ValueError as e:
            # e.g. an offset belonging to another function's feed
            res.status = falcon.HTTP_BAD_REQUEST
            res.media = {'error': str(e)}
            return

        res.media = [
            {key: value.decode() for key, value in item.items()} for item in items]
        res.status = falcon.HTTP_OK


class Dashboard(object):

    def __init__(self, conjure_funcs: List[Conjure], port: int = None, web_components_version: str = '0.0.79'):
        super().__init__()
        self.conjure_funcs = {f.identifier: f for f in conjure_funcs}
        self.port = port
        self.web_components_version = web_components_version or '0.0.79'

    def _uri(self, conj: Conjure, key: Union[str, bytes]) -> ParseResult:
        # TODO: host should not be hard coded here
        # return urlparse(f'http://localhost:{self.port}/functions/{conj.identifier}/{ensure_str(key)}')
        return uri(self.port, conj, key)


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
            res.text = content.format(
                script=script,
                imports=imports,
                style=style,
                web_components_version=self.web_components_version)
            res.set_header('content-type', 'text/html')
            res.status = falcon.HTTP_OK


class MutliFunctionApplication(falcon.API):

    def __init__(
            self,
            conjure_funcs: List[Conjure],
            port: int = None,
            web_component_version: str = None):

        super().__init__(middleware=[])
        self.functions = conjure_funcs
        self.port = port

        self.add_route('/functions', ListFunctions(conjure_funcs, port))

        self.add_route('/functions/{identifier}', Function(conjure_funcs))

        self.add_route(
            '/functions/{identifier}/indexes/{index_name}', 
            FunctionIndex(conjure_funcs))

        self.add_route('/feed/{identifier}', FunctionFeed(conjure_funcs))
        # falcon matches this literal path before the {key} route below
        self.add_route(
            '/functions/{identifier}/latest', LatestFunctionResult(conjure_funcs))
        self.add_route('/functions/{identifier}/{key}',
                       FunctionResult(conjure_funcs))
        self.add_route(
            '/dashboard',
            Dashboard(conjure_funcs, port=port, web_components_version=web_component_version))

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
        web_components_version: str = None):

    app = MutliFunctionApplication(
        conjure_funcs, port=port, web_component_version=web_components_version)

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
    print(f'Running conjure server for funcs ${", ".join(ensure_str(c.name) for c in conjure_funcs)} on port ${port}')
    return p
