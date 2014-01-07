Pymux
=====

Pure-Python TMUX clone.


About
-----

Right now this is still experimental, but I the target is to create a fully
functional tmux clone in pure Python.

Dependencies
------------

- asyncio: It requires the asyncio library for event handling. This means it
  will also require Python 3.3, but Python 3.4 is recommended. (At least the Hg
  version of 10/01/2014 required.)
- pyte: A python library for handling vt100 escape codes. (It requires the
  latest  pull requests to be applied.)


Running
-------

Right now, do: ```python run.py```
