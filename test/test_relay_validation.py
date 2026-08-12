"""A relay is untrusted: it can forge, replay or reorder anything it sends.
_is_valid_message existed and was correct, but nothing called it, so every frame
went straight into the message pool unverified."""
import json
from unittest.mock import MagicMock

import pytest

from nostr.event import Event
from nostr.filter import Filter, Filters
from nostr.key import PrivateKey
from nostr.message_pool import MessagePool
from nostr.relay import Relay
from nostr.subscription import Subscription


SUB_ID = "sub1"


@pytest.fixture
def relay():
    filters = Filters([Filter(kinds=[2022])])
    r = Relay("wss://relay.example", MessagePool(), MagicMock(), filters)
    r.subscriptions[SUB_ID] = Subscription(id=SUB_ID, filters=filters)
    return r


@pytest.fixture
def signer():
    return PrivateKey()


def frame(event, subscription_id=SUB_ID):
    return json.dumps(["EVENT", subscription_id, {
        "id": event.id, "pubkey": event.public_key,
        "created_at": event.created_at, "kind": event.kind,
        "tags": event.tags, "content": event.content, "sig": event.signature}])


def signed(signer, kind=2022, content="{}"):
    event = Event(content=content, public_key=signer.public_key.hex(), kind=kind)
    signer.sign_event(event)
    return event


class TestSignatureIsChecked:
    def test_a_properly_signed_event_is_accepted(self, relay, signer):
        assert relay._is_valid_message(frame(signed(signer))) is True

    def test_a_forged_signature_is_rejected(self, relay):
        event = Event(content="{}", public_key="aa" * 32, kind=2022)
        event.signature = "cc" * 64

        assert relay._is_valid_message(frame(event)) is False

    def test_a_signature_from_another_key_is_rejected(self, relay, signer):
        event = signed(signer)
        other = PrivateKey()
        impostor = Event(content=event.content, public_key=other.public_key.hex(),
                         created_at=event.created_at, kind=event.kind, tags=event.tags)
        impostor.signature = event.signature

        assert relay._is_valid_message(frame(impostor)) is False

    def test_tampering_with_the_content_invalidates_it(self, relay, signer):
        event = signed(signer)
        raw = json.loads(frame(event))
        raw[2]["content"] = '{"tampered": true}'

        assert relay._is_valid_message(json.dumps(raw)) is False


class TestSubscriptionAndFilters:
    def test_an_unknown_subscription_is_rejected(self, relay, signer):
        assert relay._is_valid_message(frame(signed(signer), "other")) is False

    def test_an_event_outside_the_filters_is_rejected(self, relay, signer):
        assert relay._is_valid_message(frame(signed(signer, kind=1))) is False

    def test_an_event_matching_the_filters_is_accepted(self, relay, signer):
        assert relay._is_valid_message(frame(signed(signer, kind=2022))) is True


class TestMalformedFramesAreRejectedNotRaised:
    @pytest.mark.parametrize("raw", [
        "", "   ", "not json at all", "[EVENT, broken",
        '{"a": 1}', '["EVENT"]', '["EVENT","sub1"]',
        '["EVENT","sub1",{"content":"x"}]', '["NONSENSE","sub1",{}]',
        '["EVENT","sub1",null]', '[]',
    ])
    def test_a_malformed_frame_is_rejected(self, relay, raw):
        assert relay._is_valid_message(raw) is False

    def test_notices_still_pass(self, relay):
        assert relay._is_valid_message('["NOTICE","hello"]') is True


class TestReceivePathIsGuarded:
    def test_on_message_drops_a_forged_event(self, relay):
        event = Event(content="{}", public_key="aa" * 32, kind=2022)
        event.signature = "cc" * 64

        relay._on_message(None, frame(event))

        assert relay.message_pool.has_events() is False

    def test_on_message_queues_a_valid_event(self, relay, signer):
        relay._on_message(None, frame(signed(signer)))

        assert relay.message_pool.has_events() is True

    def test_on_message_survives_a_malformed_frame(self, relay):
        relay._on_message(None, "[EVENT, broken")  # must not raise

        assert relay.message_pool.has_events() is False
