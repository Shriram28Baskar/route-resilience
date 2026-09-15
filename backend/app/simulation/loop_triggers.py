"""Cancellation-safe wait primitive for the autonomous observation scheduler."""
import asyncio


async def wait_for_loop_wakeup(
    manual_trigger: asyncio.Event,
    citizen_trigger: asyncio.Event,
    interval_s: float,
) -> None:
    """Wait for either trigger or cadence, always cancelling losing waiters."""
    waiters = [
        asyncio.create_task(manual_trigger.wait()),
        asyncio.create_task(citizen_trigger.wait()),
        asyncio.create_task(asyncio.sleep(interval_s)),
    ]
    try:
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            if not waiter.done():
                waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)
