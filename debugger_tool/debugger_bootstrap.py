#!/usr/bin/env python
# encoding: utf-8

"""
Bootstrap code which should be started by debug_wrapper.py
Probably, you will never start this file by hand. It expects centain pipes to
be established by the parent process.
"""

from bdb import Bdb

class ODB(Bdb):
    def __init__(self, socket):
        Bdb.__init__(self)
        self.socket = socket

        # Imports (attach to this class, don't pollute __main__)
        import json
        self.json = json

        # Remember input pipe attributes
        self._input_buffer = ''

    def user_line(self, frame):
        self.interaction(frame, None)

    def user_call(self, frame, argument_list):
        self.interaction(frame, None)

    def user_return(self, frame, return_value):
        self.interaction(frame, None)

    def interaction(self, frame, traceback):
        # Inform debugger
        co = frame.f_code
        self.send_to_debugger({
            'action': 'breaking',
            'data': {
                'line': frame.f_lineno,
                'filename': co.co_filename,
                'func_name': co.co_name,
            }
        })

        # Now, wait what to do:
        packet = self.get_from_debugger(blocking=True)
        action = packet['action']

        if action == 'continue':
            self.set_continue()

        elif action == 'step':
            self.set_step()

        elif action == 'next':
            self.set_next(frame)

        elif action == 'where':
            co = frame.f_code

    def run_script(self, filename):
        # Make sure this script runs in the __main__ namespace.
        # See source of pdb.
        import __main__
        #__main__.__dict__.clear()
        #__main__.__dict__.update({"__name__"    : "__main__",
        #                          "__file__"    : filename,
        #                          #"__builtins__": __builtins__,
        #                         })

        #statement = 'execfile(%r)' % filename
        #a = {"__name__"    : "__main__",
        #                          "__file__"    : filename,
        #                          #"__builtins__": __builtins__,
        #                         }
        import sys
        from bdb import BdbQuit
        self.quitting = 0
        self.reset()
        sys.settrace(self.trace_dispatch)
        try:
            execfile(filename, globals(), globals())#, a, a) # globals == locals at class level, but not here.
        except BdbQuit:
            pass
        finally:
            sys.settrace(None)

    def get_from_debugger(self, blocking=False):
        """
        Return the next json packet from the debugger. If blocking is False,
        return None when nothing is available.
        """
        while True:
            # When not enough in the buffer, read from socket.
            if not b'\n' in self._input_buffer:
                self._input_buffer += self.socket.recv(10) # XXX: keep small for debugging.

            # When we found a \n separator, return packet.
            if b'\n' in self._input_buffer:
                packet, self._input_buffer = self._input_buffer.split(b'\n', 1)
                return self.json.loads(packet.decode('utf-8'))

    def send_to_debugger(self, data):
        """
        Encode packet and send to debugger.
        (json utf8 encoded, lineline separated.)
        """
        self.socket.sendall(self.json.dumps(data).encode('utf-8') + '\n')


# Set up debugger
import sys, socket
socket = socket.fromfd(int(sys.argv[1]), socket.AF_UNIX, socket.SOCK_STREAM)
filename = sys.argv[2]
db = ODB(socket)

# Start process
print 'STARTING'
db.run_script(filename)
