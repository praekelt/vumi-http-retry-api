from twisted.internet.defer import (
    Deferred, maybeDeferred, DeferredList, inlineCallbacks)


class TaskLimiter(object):
    """
    Keeps track of a limited list of pending tasks, allowing one to request for
    a task to be added once there is a space in the list.
    """
    def __init__(self, limit, errback=None):
        self.limit = limit
        self.observers = []
        self.tasks = set()

        if errback is None:
            errback = lambda f: f

        self.errback = errback

    def add(self, fn, *a, **kw):
        """
        Request for a new task to be run once there is space. Returns a
        deferred which fires once the task has been started.
        """
        observer = Deferred()
        self.observers.append(observer)
        observer.addCallback(self._run, fn, *a, **kw)
        self._refresh()
        return observer

    @inlineCallbacks
    def done(self):
        """
        Return a deferred which fires once all the scheduled to run and tasks
        currently running have completed.
        """
        yield DeferredList(self.observers)
        yield DeferredList(list(self.tasks))

    def _run(self, _, fn, *a, **kw):
        d = maybeDeferred(fn, *a, **kw)
        self.tasks.add(d)
        d.addCallback(self._callback, d)
        d.addErrback(self._errback, d)

    def _callback(self, _, d):
        self.tasks.remove(d)
        self._refresh()

    def _errback(self, f, d):
        self._callback(None, d)
        self.errback(f)

    def _refresh(self):
        if self.observers and not self._is_full():
            self.observers.pop(0).callback(None)

    def _is_full(self):
        return len(self.tasks) >= self.limit
