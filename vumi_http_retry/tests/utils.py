from twisted.web.server import Site
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue

from klein import Klein


def pop_all(values):
    results = values[:]
    del values[:]
    return results


class ToyServer(object):
    @inlineCallbacks
    def setup(self, app=None):
        if app is None:
            app = Klein()

        self.app = app
        self.server = yield reactor.listenTCP(0, Site(self.app.resource()))
        addr = self.server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    def teardown(self):
        self.server.loseConnection()

    @classmethod
    @inlineCallbacks
    def from_test(cls, test, app=None):
        server = cls()
        yield server.setup(app)
        test.addCleanup(server.teardown)
        returnValue(server)


class ManualReadable(object):
    def __init__(self, values=None):
        self.unread = values if values is not None else []
        self.reading = []
        self.deferreds = []

    def next(self):
        if not self.reading:
            raise Exception("Nothing in `reading`")

        d = self.deferreds.pop(0)
        d.callback(self.reading.pop(0))
        return d

    def err(self, e):
        if not self.reading:
            raise Exception("Nothing in `reading`")

        self.reading.pop(0)
        d = self.deferreds.pop(0)
        d.errback(e)
        return d

    def read(self):
        d = Deferred()

        if not self.unread:
            d.callback(None)
        else:
            v = self.unread.pop(0)
            self.reading.append(v)
            self.deferreds.append(d)

        return d


class ManualWritable(object):
    def __init__(self):
        self.written = []
        self.writing = []
        self.deferreds = []

    def next(self):
        if not self.writing:
            raise Exception("Nothing in `writing`")

        self.written.append(self.writing.pop(0))
        d = self.deferreds.pop(0)
        d.callback(None)
        return d

    def err(self, e):
        if not self.writing:
            raise Exception("Nothing in `writing`")

        self.writing.pop(0)
        d = self.deferreds.pop(0)
        d.errback(e)
        return d

    def write(self, v):
        self.writing.append(v)
        d = Deferred()
        self.deferreds.append(d)
        return d


class Counter(object):
    def __init__(self):
        self.value = 0

    def inc(self):
        self.value = self.value + 1
