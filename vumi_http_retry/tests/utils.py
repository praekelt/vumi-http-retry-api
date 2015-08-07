from twisted.web.server import Site
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue

from klein import Klein


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
            raise Exception("Nothing in `reading`")

        self.writing.pop(0)
        d = self.deferreds.pop(0)
        d.errback(e)
        return d

    def write(self, v):
        self.writing.append(v)
        d = Deferred()
        self.deferreds.append(d)
        return d
