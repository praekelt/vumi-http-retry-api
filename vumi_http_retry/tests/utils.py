from twisted.web.server import Site
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from klein import Klein


class ToyServer(object):
    @inlineCallbacks
    def setup(self):
        self.app = Klein()
        self.server = yield reactor.listenTCP(0, Site(self.app.resource()))
        addr = self.server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    def teardown(self):
        self.server.loseConnection()

    @classmethod
    @inlineCallbacks
    def from_test(cls, test):
        server = cls()
        yield server.setup()
        test.addCleanup(server.teardown)
        returnValue(server)