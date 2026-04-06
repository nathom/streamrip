"""Tests for the in-process event bus.

Test Plan: EventBus

Scenario: Subscribe and receive published events
  Given an EventBus with a subscribed handler
  When an event is published on the subscribed type
  Then the handler receives the event data

Scenario: Multiple subscribers receive the same event
  Given an EventBus with two handlers subscribed to the same event type
  When an event is published
  Then both handlers receive the event

Scenario: Unsubscribed handler no longer receives events
  Given an EventBus with a subscribed handler
  When the handler is unsubscribed and an event is published
  Then the handler receives no events

Scenario: Publishing to an event type with no subscribers does not raise
  Given an EventBus with no subscribers
  When an event is published to a nonexistent type
  Then no error is raised
"""

import asyncio
import pytest
from backend.services.event_bus import EventBus


class TestEventBus:
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        async def handler(event):
            received.append(event)
        bus.subscribe("download_progress", handler)
        await bus.publish("download_progress", {"item_id": "1", "progress": 50})
        assert len(received) == 1
        assert received[0]["item_id"] == "1"

    async def test_multiple_subscribers(self):
        bus = EventBus()
        received_a, received_b = [], []
        async def handler_a(event): received_a.append(event)
        async def handler_b(event): received_b.append(event)
        bus.subscribe("test_event", handler_a)
        bus.subscribe("test_event", handler_b)
        await bus.publish("test_event", {"data": "hello"})
        assert len(received_a) == 1
        assert len(received_b) == 1

    async def test_unsubscribe(self):
        bus = EventBus()
        received = []
        async def handler(event): received.append(event)
        bus.subscribe("test", handler)
        bus.unsubscribe("test", handler)
        await bus.publish("test", {"data": "ignored"})
        assert len(received) == 0

    async def test_no_subscribers_no_error(self):
        bus = EventBus()
        await bus.publish("nonexistent_event", {"data": "test"})
