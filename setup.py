from setuptools import setup
import re

with open('README.md', 'r') as f:
    long_description = f.read()

with open('conjure/__init__.py', 'r') as fd:
    version = re.search(
        r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
        fd.read(),
        re.MULTILINE).group(1)

with open('requirements.txt', 'r') as f:
    requirements = f.readlines()

setup(
    name='conjure',
    version=version,
    url='https://github.com/JohnVinyard/conjure',
    author='John Vinyard',
    author_email='john.vinyard@gmail.com',
    long_description=long_description,
    packages=['conjure'],
    download_url=f'https://github.com/jvinyard/conjure/tarball/{version}',
    requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
)
