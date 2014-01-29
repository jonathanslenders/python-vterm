#!/usr/bin/env python
# encoding: utf-8

"""
Bootstrap code which should be started by debug_wrapper.py
Probably, you will never start this file by hand. It expects centain pipes to
be established by the parent process.
"""

from bdb import Bdb

class ODB(Bdb):
    def __init__(self, input_pipe, output_pipe):
        Bdb.__init__(self)
        self.input_pipe = input_pipe
        self.output_pipe = output_pipe

        # Imports (attach to this class, don't pollute __main__)
        import json, os, fcntl
        self.json = json
        self.os = os
        self.fcntl = fcntl

        # Remember input pipe attributes
        self._fl = fcntl.fcntl(self.input_pipe, fcntl.F_GETFL)
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
        #self.run(statement)#, a, a)

    def get_from_debugger(self, blocking=False):
        """
        Return the next json packet from the debugger. If blocking is False,
        return None when nothing is available.
        """
        # Set blocking/non blocking
        if blocking:
            self.fcntl.fcntl(self.input_pipe, self.fcntl.F_SETFL, self._fl)
        else:
            self.fcntl.fcntl(self.input_pipe, self.fcntl.F_SETFL, self._fl | self.os.O_NONBLOCK)

        # Read packet.
        packet = self.input_pipe.readline()
        if packet and packet[-1] == '\n':
            packet = self._input_buffer + packet
            self._input_buffer = ''
            return self.json.loads(packet.decode('utf-8'))
        else:
            self._input_buffer += packet
            return None

    def send_to_debugger(self, data):
        """
        Encode packet and send to debugger.
        (json utf8 encoded, lineline separated.)
        """
        self.output_pipe.write(self.json.dumps(data).encode('utf-8') + '\n')
        self.output_pipe.flush()


# Set up debugger
import os, sys
output_pipe = os.fdopen(int(sys.argv[1]), 'w')
input_pipe = os.fdopen(int(sys.argv[2]), 'r')
filename = sys.argv[3]
db = ODB(input_pipe, output_pipe)

# Start process
print 'STARTING'
db.run_script(filename)
