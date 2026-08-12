"""Python 3.11 tightened the dataclass rule on mutable defaults: a field whose
default is an unhashable class instance is rejected at class creation time.
RelayPolicy is a dataclass, so it is unhashable, and `policy: RelayPolicy =
RelayPolicy()` made the whole package fail to import on 3.11 and later."""
import dataclasses
import importlib

import pytest


class TestNoMutableDataclassDefaults:
    @pytest.mark.parametrize("module_name,class_name", [
        ("nostr.relay", "Relay"),
        ("nostr.relay", "RelayPolicy"),
        ("nostr.relay", "RelayProxyConnectionConfig"),
        ("nostr.relay_manager", "RelayManager"),
        ("nostr.subscription", "Subscription"),
    ])
    def test_no_field_has_a_mutable_default(self, module_name, class_name):
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name, None)
        if cls is None or not dataclasses.is_dataclass(cls):
            pytest.skip(f"{class_name} is not a dataclass")

        for f in dataclasses.fields(cls):
            if f.default is dataclasses.MISSING:
                continue
            assert f.default.__class__.__hash__ is not None, (
                f"{class_name}.{f.name} defaults to an unhashable "
                f"{type(f.default).__name__}; use field(default_factory=...)")

    def test_relay_policy_comes_from_a_factory(self):
        from nostr.relay import Relay
        policy_field = next(f for f in dataclasses.fields(Relay) if f.name == "policy")

        assert policy_field.default is dataclasses.MISSING
        assert policy_field.default_factory is not dataclasses.MISSING

    def test_two_relays_do_not_share_a_policy_object(self):
        # the practical reason default_factory is required
        from unittest.mock import MagicMock
        from nostr.relay import Relay
        from nostr.message_pool import MessagePool
        from nostr.filter import Filters

        a = Relay("wss://a", MessagePool(), MagicMock(), Filters([]))
        b = Relay("wss://b", MessagePool(), MagicMock(), Filters([]))

        assert a.policy is not b.policy


class TestPackageImports:
    @pytest.mark.parametrize("module_name", [
        "nostr.relay", "nostr.relay_manager", "nostr.event", "nostr.key",
        "nostr.filter", "nostr.message_pool", "nostr.message_type",
        "nostr.subscription",
    ])
    def test_module_imports(self, module_name):
        assert importlib.import_module(module_name) is not None
