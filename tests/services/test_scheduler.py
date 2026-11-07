import asyncio

import pytest

from src.services import CycleReport, DeliveryReport, PollingScheduler, ServiceSettings

pytestmark = pytest.mark.asyncio(loop_scope="session")


class FakePolling:
    def __init__(self):
        self.calls = 0
        self.fail = False

    async def run_cycle(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return CycleReport()


class FakeDelivery:
    def __init__(self):
        self.calls = 0

    async def deliver_pending(self):
        self.calls += 1
        return DeliveryReport()


class FakeCatalog:
    def __init__(self):
        self.refresh_calls = 0

    async def refresh_all(self):
        self.refresh_calls += 1
        return {}


async def wait_until(condition, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        assert loop.time() < deadline, "условие не выполнилось вовремя"
        await asyncio.sleep(0.01)


async def test_run_once_polls_and_delivers():
    polling, delivery = FakePolling(), FakeDelivery()
    scheduler = PollingScheduler(polling, delivery, FakeCatalog(), ServiceSettings())

    cycle, delivered = await scheduler.run_once()

    assert isinstance(cycle, CycleReport) and isinstance(delivered, DeliveryReport)
    assert (polling.calls, delivery.calls) == (1, 1)


async def test_run_once_still_delivers_when_polling_fails():
    polling, delivery = FakePolling(), FakeDelivery()
    polling.fail = True
    scheduler = PollingScheduler(polling, delivery, FakeCatalog(), ServiceSettings())

    cycle, delivered = await scheduler.run_once()

    assert cycle is None
    assert isinstance(delivered, DeliveryReport)
    assert delivery.calls == 1


async def test_start_runs_cycles_periodically_and_stop_halts_them():
    polling = FakePolling()
    scheduler = PollingScheduler(
        polling, FakeDelivery(), FakeCatalog(), ServiceSettings(poll_interval_seconds=0.02)
    )

    scheduler.start()
    await wait_until(lambda: polling.calls >= 3)
    await scheduler.stop()

    calls_after_stop = polling.calls
    await asyncio.sleep(0.1)
    assert polling.calls == calls_after_stop


async def test_filters_are_refreshed_when_due():
    catalog = FakeCatalog()
    settings = ServiceSettings(poll_interval_seconds=0.02, filters_refresh_interval_seconds=0)
    scheduler = PollingScheduler(FakePolling(), FakeDelivery(), catalog, settings)

    scheduler.start()
    await wait_until(lambda: catalog.refresh_calls >= 1)
    await scheduler.stop()
