from libpymux.panes import ExecPane
import os

class BashPane(ExecPane):
    def _do_exec(self):
        os.execv('/bin/bash', ['bash'])

