from twisted.trial.unittest import TestCase
from twisted.internet.defer import Deferred, inlineCallbacks

from vumi_http_retry.limiter import DeferredLimiterOverflow, DeferredLimiter


class TestDeferredLimiter(TestCase):
    def test_full(self):
        limiter = DeferredLimiter(2)
        self.assertFalse(limiter.full)

        limiter.add(Deferred())
        self.assertFalse(limiter.full)

        limiter.add(Deferred())
        self.assertTrue(limiter.full)

    def test_count(self):
        limiter = DeferredLimiter(2)
        self.assertEqual(limiter.count, 0)

        limiter.add(Deferred())
        self.assertEqual(limiter.count, 1)

        limiter.add(Deferred())
        self.assertEqual(limiter.count, 2)

    def test_add_overflow(self):
        limiter = DeferredLimiter(2)
        limiter.add(Deferred())
        limiter.add(Deferred())
        self.assertRaises(DeferredLimiterOverflow, limiter.add, Deferred)
        self.assertRaises(DeferredLimiterOverflow, limiter.add, Deferred)

    @inlineCallbacks
    def test_when_not_full(self):
        limiter = DeferredLimiter(2)
        d1 = limiter.add(Deferred())
        limiter.add(Deferred())
        d = limiter.when_not_full()

        self.assertTrue(limiter.full)
        d1.callback(None)
        self.assertFalse(limiter.full)

        self.assertEqual((yield d), 1)
        self.assertFalse(limiter.full)

        d3 = limiter.add(Deferred())
        d = limiter.when_not_full()

        self.assertTrue(limiter.full)
        d3.callback(None)
        self.assertFalse(limiter.full)

        self.assertEqual((yield d), 1)
        self.assertFalse(limiter.full)

    @inlineCallbacks
    def test_when_not_full_errback(self):
        limiter = DeferredLimiter(2)
        d1 = limiter.add(Deferred())
        limiter.add(Deferred())
        d = limiter.when_not_full()

        self.assertTrue(limiter.full)
        d1.errback(Exception())
        self.assertFalse(limiter.full)

        self.assertEqual((yield d), 1)
        self.assertFalse(limiter.full)

        d3 = limiter.add(Deferred())
        d = limiter.when_not_full()

        self.assertTrue(limiter.full)
        d3.errback(Exception())
        self.assertFalse(limiter.full)

        self.assertEqual((yield d), 1)

    @inlineCallbacks
    def test_cancel(self):
        cancelled = []

        def canceller(d):
            d.callback(None)
            cancelled.append(d)

        limiter = DeferredLimiter(3)
        d1 = limiter.add(Deferred(canceller))
        d2 = limiter.add(Deferred(canceller))
        d3 = limiter.add(Deferred(canceller))
        d3.callback(None)

        self.assertEqual(cancelled, [])
        limiter.cancel()

        yield d1
        yield d2

        self.assertEqual(cancelled, [d1, d2])

    @inlineCallbacks
    def test_errback(self):
        errs = []

        def errback(f):
            errs.append(f.value)

        limiter = DeferredLimiter(2, errback)
        d1 = limiter.add(Deferred())
        d2 = limiter.add(Deferred())

        e1 = Exception()
        d1.errback(e1)

        yield d1
        self.assertEqual(errs, [e1])

        d3 = limiter.add(Deferred())
        e2 = Exception()
        d3.errback(e2)

        yield d3
        self.assertEqual(errs, [e1, e2])
