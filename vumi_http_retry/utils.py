from twisted.internet.defer import Deferred, inlineCallbacks, DeferredLock


def run_concurrently(limit, next_task, run_task, errback=None):
    runner = ConcurrentRunner(limit, next_task, run_task, errback)
    runner.fill()
    return runner.d


class ConcurrentRunner(object):
    def __init__(self, limit, next_value, run_task, errback=None):
        if errback is None:
            errback = lambda x: x
        self.errback = errback
        self.jobs = set()
        self.lock = DeferredLock()
        self.end_of_values = False
        self.d = Deferred(lambda _: self.cancel())
        self.limit = limit
        self.next = next_value
        self.run = run_task

    def cancel(self):
        while self.jobs:
            self.jobs.pop().cancel()

    @inlineCallbacks
    def fill(self):
        yield self.lock.acquire()

        while not self.end_of_values and len(self.jobs) < self.limit:
            d = self.next()
            d.addErrback(self.err)
            v = yield d

            if v is None:
                self.end_of_values = True
                break

            d = self.run(v)
            d.addCallback(self.job_done, d)
            d.addErrback(self.job_err, d)
            self.jobs.add(d)

        if not self.jobs:
            self.d.callback(None)

        self.lock.release()

    def job_done(self, _, d):
        self.jobs.remove(d)
        self.fill()

    def job_err(self, f, d):
        self.err(f)
        self.job_done(None, d)

    def err(self, f):
        self.errback(f)
