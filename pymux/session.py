from libpymux.session import Session
from libpymux.log import logger
from libpymux.window import Window

from pymux.panes import BashPane

import asyncio
import concurrent


class PyMuxSession(Session):
    def __init__(self):
        super().__init__()
        self.pane_executor = concurrent.futures.ThreadPoolExecutor(1024)
        self.pane_runners = [ ] # Futures

        # Create first window/pane.
        self.create_new_window()

    def create_new_window(self):
        logger.info('create_new_window')
        window = Window()
        self.add_window(window)

        pane = BashPane(self.pane_executor)
        window.add_pane(pane)
        self._run_pane(window, pane)


    def split_pane(self, vsplit):
        pane = BashPane(self.pane_executor)
        self.active_window.add_pane(pane, vsplit=vsplit)
        self._run_pane(self.active_window, pane)

    def _run_pane(self, window, pane):
        # Create coroutine which handles the creation/deletion of this pane in
        # the session.
        f = None

        @asyncio.coroutine
        def run_pane():
            yield from pane.run()
            self.pane_runners.remove(f)

            # Focus next pane in this window when this one was focussed.
            if len(window.panes) > 1 and window.active_pane == pane:
                window.focus_next()

            pane.parent.remove(pane)
            window.panes.remove(pane)

            # When this window doesn't contain any panes anymore. Remove window
            # from session.
            if len(window.panes) == 0:
                self.windows.remove(window)
                if window == self.active_window:
                    if self.windows:
                        self.active_window = self.windows[0]
                    else:
                        self.active_window = None

            self.invalidate(Redraw.All)

        f = asyncio.async(run_pane())
        self.pane_runners.append(f)

    @asyncio.coroutine
    def run(self):
        """ Run until we don't have panes anymore. """
        while True:
            runners = self.pane_runners
            if runners:
                #yield from asyncio.gather(* runners)

                # Wait until one pane is ready
                done, pending = yield from asyncio.wait(
                        runners, return_when=asyncio.tasks.FIRST_COMPLETED)

            else:
                break
