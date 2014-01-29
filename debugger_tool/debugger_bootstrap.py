#!/usr/bin/env python
# encoding: utf-8

import fcntl
import json
import os
import sys

from bdb import Bdb

class ODB(Bdb):
    def user_line(self, frame):
        self.interaction(frame, None)

    def user_call(self, frame, argument_list):
        self.interaction(frame, None)

    def user_return(self, frame, return_value):
        self.interaction(frame, None)

    def interaction(self, frame, traceback):
        # Inform debugger
        co = frame.f_code
        db.send_to_debugger({
            'action': 'breaking',
            'data': {
                'line': frame.f_lineno,
                'filename': co.co_filename,
                'func_name': co.co_name,
            }
        })

        # Now, wait what to do:
        packet = db.get_from_debugger(blocking=True)
        action = packet['action']

        if action == 'continue':
            self.set_continue()

        elif action == 'step':
            self.set_step()

        elif action == 'next':
            self.set_next(frame)

        elif action == 'where':
            co = frame.f_code


class DebuggerConnection:
    def __init__(self):
        self.output_pipe = os.fdopen(int(sys.argv[1]), 'w')
        self.input_pipe = os.fdopen(int(sys.argv[2]), 'r')

        # Remember input pipe attributes
        self._fl = fcntl.fcntl(self.input_pipe, fcntl.F_GETFL)
        self._input_buffer = ''

    def get_from_debugger(self, blocking=False):
        """
        Return the next json packet from the debugger. If blocking is False,
        return None when nothing is available.
        """
        # Set blocking/non blocking
        if blocking:
            fcntl.fcntl(self.input_pipe, fcntl.F_SETFL, self._fl)
        else:
            fcntl.fcntl(self.input_pipe, fcntl.F_SETFL, self._fl | os.O_NONBLOCK)

        # Read packet.
        packet = self.input_pipe.readline()
        if packet and packet[-1] == '\n':
            packet = self._input_buffer + packet
            self._input_buffer = ''
            return json.loads(packet.decode('utf-8'))
        else:
            self._input_buffer += packet
            return None

    def send_to_debugger(self, data):
        """
        Encode packet and send to debugger.
        (json utf8 encoded, lineline separated.)
        """
        self.output_pipe.write(json.dumps(data).encode('utf-8') + '\n')
        self.output_pipe.flush()


def c(input):
    print 'input =', input
    print 'Leaving c()'

def b(arg):
    val = arg * 5
    c(val)
    print 'Leaving b()'

def a():
    b(2)
    print 'Leaving a()'

TRACE_INTO = ['b']

db = DebuggerConnection()
print 'STARTING'
ODB().set_trace()


a()
a()
a()


sys.settrace(None)
