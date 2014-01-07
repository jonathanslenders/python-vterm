import datetime

class StatusBar:
    @property
    def right_text(self):
        return datetime.datetime.now().isoformat()

    @property
    def left_text(self):
        return 'pymux'
