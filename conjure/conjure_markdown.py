import argparse
import os
from os import PathLike
import conjure
import re


class CodeBlock(object):

    def __init__(self, source: str):
        super().__init__()
        self._raw = source

    @property
    def markdown(self):
        return f'\n```python\n{self._raw}```\n'

    @property
    def raw(self):
        return self._raw

    @property
    def normalized(self):
        return '\n'.join(filter(lambda x: bool(x), self._raw.splitlines()))

    def get_result(self, glob: dict):
        bytecode = compile(self.normalized, 'placeholder.dat', mode='exec')
        exec(bytecode, glob)
        return glob.get('_', None)


class EmbeddedCodeBlock(object):

    pattern = re.compile(r'```python:\s+(?P<code>[^`]+)```')

    def __init__(self, block: CodeBlock, start: int, span: int, position: int):
        super().__init__()
        self._block = block
        self._start = start
        self._span = span
        self._position = position

    def get_result(self, glob: dict):
        result = self._block.get_result(glob)
        return glob, result

    @property
    def markdown(self):
        return self._block.markdown

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._start + self._span

    @property
    def raw(self):
        return self._block.raw

    @classmethod
    def extract_all(cls, markdown: str):
        for i, m in enumerate(cls.pattern.finditer(markdown)):
            yield EmbeddedCodeBlock(
                CodeBlock(m.groupdict()['code']),
                start=m.start(),
                span=m.end() - m.start(),
                position=i)


def render_html(
        markdown_path: PathLike,
        output_path: PathLike,
        storage_path: PathLike,
        s3_bucket: str) -> dict:

    with open(markdown_path, 'r') as f:
        content = f.read()

        code_blocks = list(EmbeddedCodeBlock.extract_all(content))

        print(f'found {len(code_blocks)} code blocks')

        if len(code_blocks) == 0:
            with open(output_path, 'w') as output_file:
                output_file.write(content)
                return

        storage = conjure.LocalCollectionWithBackup(
            local_path=storage_path,
            remote_bucket=s3_bucket,
            is_public=True,
            cors_enabled=True)

        g = {'conjure_storage': storage}
        current_pos = 0

        chunks = []
        for i, block in enumerate(code_blocks):
            print('======================================')
            
            chunks.append(content[current_pos:block.start])
            chunks.append(block.markdown)
            current_pos = block.end + 1

            print(f'Computing block {i}')
            try:
                g, result = block.get_result(dict(**g))
            except Exception as e:
                print(f'Failed to compute block {i} with error {e}')

            if '_' in g:
                try:
                    # render html that conjure will pick up and transform
                    # TODO: only do this for jekyll?
                    chunks.append(f'{result.conjure_html()}')
                    print('rendered block as conjure')
                    print(result.public_uri)
                    print(result.content_type)
                except AttributeError:
                    # render output as text
                    chunks.append(f'`{g["_"]}`')
                    print('rendered block as text')

            try:    
                del g['_']
            except KeyError:
                pass


        chunks.append(content[current_pos:])

        markdown = '\n'.join(chunks)
        with open(output_path, 'w') as output_file:
            output_file.write(markdown)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--markdown',
        required=True,
        type=str,
        help='Path to the markdown file used to generate output')
    parser.add_argument(
        '--output',
        required=True,
        type=str,
        help='Path where the output html should be saved')
    parser.add_argument(
        '--storage',
        required=True,
        type=str,
        help='Path where local results should be cached')
    parser.add_argument(
        '--s3',
        required=True,
        type=str,
        help='The s3 bucket where code block results should be stored')
    parser.add_argument(
        '--watch',
        default=False,
        action='store_true',
        help='Watch the markdown file for changes and regenerate html when detected')

    args = parser.parse_args()

    if os.path.isfile(args.output):
        output_path = args.output
    else:
        md_filename = os.path.basename(args.markdown)
        output_path = os.path.join(args.output, md_filename)

    render_html(args.markdown, output_path, args.storage, args.s3)

    if args.watch:
        import inotify.adapters
        notify = inotify.adapters.Inotify()
        notify.add_watch(args.markdown)
        for event in notify.event_gen(yield_nones=False):
            (_, type_names, path, filename) = event
            if 'IN_CLOSE_WRITE' in type_names:
                render_html(args.markdown, output_path,
                            args.storage, args.s3)
