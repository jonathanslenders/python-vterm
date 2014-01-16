#!/usr/bin/env python

"""Usage:
  pymux.py run
  pymux.py server
  pymux.py attach
  pymux.py session-info
"""

import sys
import docopt
from pymux import __version__


from pymux.run.socket_client import start_client
from pymux.run.socket_server import start_server
from pymux.run.standalone import start_standalone


def start(name=sys.argv[0]):
    """
    Entry point for a pymux client.
    """
    a = docopt.docopt(__doc__.replace('pymux.py', name), version=__version__)

    if a['run']:
        start_standalone()

    elif a['server']:
        start_server()

    elif a['attach']:
        start_client()

if __name__ == '__main__':
    start()
