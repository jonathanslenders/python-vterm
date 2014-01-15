#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
        name='pymux',
        author='Jonathan Slenders',
        version='0.1',
        license='LICENSE.txt',
        #url='https://github.com/jonathanslenders/asyncio-amp',
        scripts=['pymux/bin/pymux'],
        description='Python terminal multiplexer (Pure Python tmux clone)',
        long_description=open("README.rst").read(),
        packages=['pymux'],
        install_requires = [ 'asyncio', 'pyte' ],
)
