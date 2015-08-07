from twisted.internet.defer import (
    Deferred, inlineCallbacks, DeferredLock, maybeDeferred)


class TaskLimiter(object):
    """
    Keeps track of a limited list of pending tasks, allowing one to request for
    a task to be added once there is a vacancy in the list.
    """
    def __init__(self, limit, errback=None):
        self.lock = DeferredLock()
        self.limit = limit
        self.observers = []
        self.tasks = set()

        if errback is None:
            errback = lambda f: f

        self.errback = errback

    @inlineCallbacks
    def add(self, fn, *a, **kw):
        observer = Deferred()
        self.observers.append(observer)
        observer.addCallback(self._run, fn, *a, **kw)
        yield self._refresh()
        yield observer

    def _run(self, _, fn, *a, **kw):
        d = maybeDeferred(fn, *a, **kw)
        self.tasks.add(d)
        d.addCallback(self._callback, d)
        d.addErrback(self._errback, d)

    @inlineCallbacks
    def _callback(self, _, d):
        self.tasks.remove(d)
        yield self._refresh()

    @inlineCallbacks
    def _errback(self, f, d):
        yield self._callback(None, d)
        self.errback(f)

    @inlineCallbacks
    def _refresh(self):
        yield self.lock.acquire()

        if self.observers and not self._is_full():
            self.observers.pop(0).callback(None)

        self.lock.release()

    def _is_full(self):
        return len(self.tasks) >= self.limit
