#!/usr/bin/env python

"""Usage:
  pymux.py run
  pymux.py server
  pymux.py attach
  pymux.py session-info
  pymux.py new-window
"""

import sys
import docopt
import pprint
from pymux import __version__


from pymux.run.socket_client import start_client
from pymux.run.socket_server import start_server
from pymux.run.standalone import start_standalone
from pymux.run.utils import session_info, new_window


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

    elif a['session-info']:
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(session_info())

    elif a['new-window']:
        new_window()


if __name__ == '__main__':
    start()
