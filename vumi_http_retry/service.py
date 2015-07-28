import yaml

from twisted.python import usage
from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks


class BaseOptions(usage.Options):
    optParameters = [[
        'config', 'c', None,
        'Path to the config file to read from'
    ]]


class BaseService(MultiService, object):
    WORKER_CLS = None

    def __init__(self, config):
        super(BaseService, self).__init__()
        self.worker = self.WORKER_CLS(config)

    @classmethod
    def load_config(cls, filename):
        return yaml.safe_load(open(filename))

    @classmethod
    def from_options(cls, options):
        config = {}

        if options['config'] is not None:
            config = cls.load_config(options['config'])

        return cls(config)

    @inlineCallbacks
    def startService(self):
        yield super(BaseService, self).startService()
        yield self.worker.setup()

    @inlineCallbacks
    def stopService(self):
        yield self.worker.teardown()
        yield super(BaseService, self).stopService()
