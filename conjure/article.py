import os.path
from typing import Any, Dict, Iterable, Literal, Tuple, Union
import tokenize
from urllib.parse import ParseResult

import markdown
from io import BytesIO
import re

ChunkType = Literal['CODE', 'MARKDOWN']

RenderTarget = Literal['html', 'markdown']


def build_template(page_title: str, content: str, toc: str):
    template = f'''
        <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <meta http-equiv="X-UA-Compatible" content="ie=edge">
                <title>{page_title}</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&display=swap" rel="stylesheet">
                <script src="https://cdn.jsdelivr.net/gh/JohnVinyard/web-components@v0.0.12/build/components/bundle.js"></script>
                <style>
                    body {{
                        font-family: "Gowun Batang", serif;
                        margin: 20px 100px;
                        color: #333;
                        background-color: #f0f0f0;
                    }}
                    .back-to-top {{
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        background-color: #333;
                        color: #f0f0f0;
                        padding: 10px;
                        font-size: 0.9em;
                    }}
                    img {{
                        width: 100%;
                    }}
                    ul {{
                        list-style-type: none;
                        padding-inline-start: 20px;
                        font-size: 20px;
                    }}
                    a {{
                        color: #660000;
                    }}
                    a:visited {{
                        color: #000066;
                    }}
                    caption {{
                        text-decoration: underline;
                        font-size: 0.6em;
                    }}
                    blockquote {{
                        background-color: #d5d5d5;
                        padding: 2px 10px;
                    }}
                </style>
            </head>
            <body>
                {toc}
                {content}

                <a href="#">
                    <div class="back-to-top">
                        Back to Top
                    </div>
                </a>

            </body>
            </html>
    '''
    return template


class BytesContext:

    def __init__(self):
        super().__init__()
        self.bio = BytesIO()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class ImageComponent:
    def __init__(self, src: Union[str, ParseResult], height: int):
        super().__init__()

        try:
            self.src = src.geturl()
        except AttributeError:
            self.src = src

        self.height = height

    def render(self, target: RenderTarget):
        if target == 'html':
            return self.html()
        elif target == 'markdown':
            return self.markdown()
        else:
            raise ValueError(f'Unknown render type "{target}"')

    def html(self):
        return f'''
        <img src="{self.src}"></img>
        '''

    def markdown(self):
        raise NotImplementedError('This component cannot be converted to markdown')


class CitationComponent:
    def __init__(self, tag: str, author: str, url: str, header: str, year: str):
        super().__init__()
        self.tag = tag
        self.author = author
        self.url = url
        self.header = header
        self.year = year

    def render(self, target: RenderTarget):
        if target == 'html':
            return self.html()
        elif target == 'markdown':
            return self.markdown()
        else:
            raise ValueError(f'Unknown render type "{target}"')

    def html(self):
        return f'''
        <citation-block
            tag="{self.tag}"
            author="{self.author}"
            url="{self.url}"
            header="{self.header}"
            year="{self.year}">
        </citation-block>
        '''

    def markdown(self):
        raise NotImplementedError('This component cannot be converted to markdown')


class AudioComponent:
    def __init__(
            self, src: Union[str, ParseResult],
            height: int,
            scale: int = 1,
            controls: bool = True,
            samples: int = 256):

        super().__init__()

        try:
            self.src = src.geturl()
        except AttributeError:
            self.src = src

        self.height = height
        self.scale = scale
        self.controls = controls
        self.samples = samples

    def render(self, target: RenderTarget):
        if target == 'html':
            return self.html()
        elif target == 'markdown':
            return self.markdown()
        else:
            raise ValueError(f'Unknown render type "{target}"')

    def html(self):
        return f'''
        <audio-view
            src="{self.src}"
            height="{self.height}"
            samples="{self.samples}"
            scale="{self.scale}"
            {'controls' if self.controls else ''}
        ></audio-view>'''

    def markdown(self):
        raise NotImplementedError('This component cannot be converted to markdown')


class CompositeComponent:
    def __init__(self, *args):
        super().__init__()
        self.components = args

    def render(self, target: RenderTarget):
        if target == 'html':
            return self.html()
        elif target == 'markdown':
            return self.markdown()
        else:
            raise ValueError(f'Unknown render type "{target}"')

    def _iter_rendered_content(self):
        for component in self.components:
            if isinstance(component, str):
                yield markdown.markdown(component)
            else:
                yield component.html()

    def html(self) -> str:
        return '\n'.join(self._iter_rendered_content())

    def markdown(self):
        raise NotImplementedError('This component cannot be converted to markdown')


def chunk_article(filepath: str, target: RenderTarget, **kwargs) -> Iterable[Tuple[str, int, int]]:
    with open(filepath, 'rb') as f:
        structure = tokenize.tokenize(f.readline)

        for item in structure:
            if item.type == tokenize.STRING and item.string.startswith('"""[markdown]'):
                no_quotes = item.string.replace('"""', '')
                no_markdown = no_quotes.replace('[markdown]', '')
                markup = markdown.markdown(no_markdown)
                start, end = item.start[0], item.end[0]
                yield (markup, start, end)
            elif item.type == tokenize.COMMENT:
                content = item.string.replace('# ', '')
                try:
                    component = kwargs[content]
                    rendered = component.render(target)
                    start, end = item.start[0], item.end[0] + 1
                    yield (rendered, start, end)
                except KeyError:
                    continue


def classify_chunks(filepath: str, target: RenderTarget, **kwargs) -> Iterable[Tuple[ChunkType, str]]:
    with open(filepath, 'r') as f:
        lines = list(f.readlines())

    chunks = list(chunk_article(filepath, target, **kwargs))

    current_line = 0

    for markup, start, end in chunks:

        if start > current_line:
            yield ('CODE', '\n'.join(lines[current_line: start - 1]))
            current_line = start

        yield ('MARKDOWN', markup)
        current_line = end

    yield ('CODE', '\n'.join(lines[current_line:]))


header_pattern = r'<a\sid=\"(?P<id>[^\"]+)\".*\n\s*<(?P<header>h\d)>(?P<title>[^<]+)'

pattern = r'(?P<x><h\d>(?P<title>[^<]+)</h\d>\n)'


def generate_table_of_contents(
        html: str,
        title: str = 'Table of Contents',
        max_depth: int = 2) -> Tuple[str, str]:

    # first, add anchor links to the html
    p = re.compile(pattern)

    def replacer(m) -> str:
        gd = m.groupdict()
        replacement = f'''
<a id="{gd['title']}"></a>
{gd['x']}'''
        return replacement

    html = p.sub(replacer, html)

    p = re.compile(header_pattern)

    # then scan all the anchor link and header pairs to produce a table
    # of contents

    markdown_content = f'''
# {title}

<caption>Table of Contents</caption>

'''
    tab = '\t'

    for match in p.finditer(html):
        d = match.groupdict()
        _id, tag, title = d['id'], d['header'], d['title']
        indent = int(tag[-1:]) - 1

        if indent > max_depth:
            continue

        entry = f'{tab * indent} - [{title}](#{_id})\n'
        markdown_content += entry

    html_toc = markdown.markdown(markdown_content)
    return html, html_toc


def conjure_article(
        filepath: str,
        target: RenderTarget,
        title: Union[str, None] = None,
        max_depth: int = 1,
        **kwargs: Dict[str, Any]):
    final_chunks = classify_chunks(filepath, target, **kwargs)

    content = ''

    for i, ch in enumerate(final_chunks):
        t, new_content = ch

        new_content = new_content.strip()

        if t == 'CODE' and len(new_content):
            content += f'\n<code-block language="python">{new_content}</code-block>\n'
        elif t == 'MARKDOWN':
            content += f'\n{new_content}\n'

    content, toc = generate_table_of_contents(
        content, title=title, max_depth=max_depth)

    name, _ = os.path.splitext(filepath)

    filename = f'{name}.html'
    with open(filename, 'w') as f:
        f.write(build_template('Blah', content, toc))

    wd = os.getcwd()
    full_path = os.path.join(wd, filename)
