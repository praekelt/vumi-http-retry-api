class BaseWorker(object):
    CONFIG_CLS = None

    def __init__(self, config=None):
        if config is None:
            config = {}

        self.config = self.CONFIG_CLS(config)

    def setup(self):
        raise NotImplementedError()

    def teardown(self):
        raise NotImplementedError()
