import datetime

class StatusBar:
    def __init__(self, get_client_func):
        self._get_client_func = get_client_func

    @property
    def right_text(self):
        return datetime.datetime.now().isoformat()

    @property
    def left_text(self):
        result = ['pymux']
        client = self._get_client_func()

        for w in client.windows:
            if client.active_window == w:
                result.append('[%s]' % id(w))
            else:
                result.append(' %s ' % id(w))

        return ' '.join(result)
