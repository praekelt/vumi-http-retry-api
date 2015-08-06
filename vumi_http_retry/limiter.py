from itertools import ifilterfalse

from twisted.internet.defer import Deferred, succeed


class DeferredLimiterOverflow(Exception):
    """Raised when one attempts to add to a full DeferredLimiter"""


class DeferredLimiter(object):
    """
    Keeps track of a limited list of pending deferreds, allowing one to wait for
    a vacancy in the list when one of the deferreds is done.
    """
    def __init__(self, limit, errback=None):
        self.limit = limit
        self.deferreds = []
        self.observers = []

        if errback is None:
            errback = lambda f: f

        self.errback = errback

    @property
    def full(self):
        return self.count >= self.limit

    @property
    def count(self):
        return len(self.deferreds)

    def add(self, d):
        if self.full:
            raise DeferredLimiterOverflow()

        self.deferreds.append(d)
        d.addCallback(self._callback, d)
        d.addErrback(self._errback, d)
        return d

    def when_not_full(self):
        d = Deferred()
        self.observers.append(d)
        self._refresh()
        return d

    def cancel(self):
        for d in self.deferreds[:]:
            d.cancel()

    def _callback(self, _, d):
        self.deferreds.remove(d)
        self._refresh()

    def _refresh(self):
        if self.full:
            return

        for d in self.observers:
            d.callback(self.count)

        self.observers = []

    def _errback(self, f, d):
        self._callback(None, d)
        self.errback(f)
