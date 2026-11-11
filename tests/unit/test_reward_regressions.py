import unittest
from types import SimpleNamespace
from unittest.mock import patch

from monopolygo_rewards import rewards


class RewardDecisionTests(unittest.TestCase):
    def test_profile_requires_success_and_exact_displayed_name(self):
        profile = {
            "IsSuccess": True,
            "Data": {"Name": "internal-name", "DisplayName": "WonderfulFinch83"},
        }
        self.assertEqual(rewards.verify_identity(profile, "WonderfulFinch83"), "WonderfulFinch83")
        for bad in [
            {},
            {"IsSuccess": False, "Data": profile["Data"]},
            {"IsSuccess": True, "Data": {"DisplayName": "OtherUser"}},
            {"IsSuccess": True, "Data": {"Name": "WonderfulFinch83"}},
            {"IsSuccess": True, "Data": {"Name": "WonderfulFinch83", "DisplayName": "OtherUser"}},
        ]:
            with self.subTest(profile=bad), self.assertRaises(rewards.WorkflowError):
                rewards.verify_identity(bad, "WonderfulFinch83")

    def test_free_wheel_requires_explicit_available_zero_cost_wheel(self):
        wheel = {"Key": "free-wheel", "PointsCost": 0, "Available": True}
        data = {"FreeSpinAvailable": True, "Wheels": [wheel]}
        self.assertEqual(rewards.free_wheel_key(data), "free-wheel")
        for change in [
            {"PointsCost": 400},
            {"PointsCost": False},
            {"Available": False},
            {"Key": ""},
        ]:
            with self.subTest(change=change), self.assertRaises(rewards.WorkflowError):
                rewards.free_wheel_key({**data, "Wheels": [{**wheel, **change}]})

    def test_explicit_unavailable_wheel_is_skipped(self):
        self.assertIsNone(rewards.free_wheel_key({"FreeSpinAvailable": False}))

    def test_missing_or_ambiguous_wheel_state_is_rejected(self):
        wheel = {"Key": "free", "PointsCost": 0, "Available": True}
        for bad in [
            {},
            {"FreeSpinAvailable": "true"},
            {"FreeSpinAvailable": True, "Wheels": [wheel, wheel]},
        ]:
            with self.subTest(data=bad), self.assertRaises(rewards.WorkflowError):
                rewards.free_wheel_key(bad)

    def test_gift_requires_defined_and_explicit_availability(self):
        self.assertTrue(
            rewards.gift_available({"FreeGiftDefined": True, "FreeGiftAvailable": True})
        )
        self.assertFalse(
            rewards.gift_available({"FreeGiftDefined": True, "FreeGiftAvailable": False})
        )
        for bad in [
            {},
            {"FreeGiftDefined": False, "FreeGiftAvailable": True},
            {"FreeGiftDefined": True, "FreeGiftAvailable": "true"},
        ]:
            with self.subTest(data=bad), self.assertRaises(rewards.WorkflowError):
                rewards.gift_available(bad)

    def test_claim_confirmation_rejects_failed_and_paid_wheel_results(self):
        payload = {"IsSuccess": True, "Data": {"UnlockedBenefit": {"PointsCost": 0}}}
        rewards.verify_claim(payload, "wheel")
        for bad in [
            {},
            {"IsSuccess": False, "Data": payload["Data"]},
            {"IsSuccess": True, "Data": {"UnlockedBenefit": {"PointsCost": 400}}},
        ]:
            with self.subTest(payload=bad), self.assertRaises(rewards.WorkflowError):
                rewards.verify_claim(bad, "wheel")
        rewards.verify_claim(
            {
                "IsSuccess": True,
                "Data": {"FreeGiftAvailable": False, "NextFreeGift": "2026-11-08T12:00:00Z"},
            },
            "gift",
        )
        with self.assertRaises(rewards.WorkflowError):
            rewards.verify_claim({"IsSuccess": True, "Data": {"FreeGiftAvailable": True}}, "gift")

    def test_gift_claim_next_reset_does_not_require_availability_flag(self):
        rewards.verify_claim(
            {
                "IsSuccess": True,
                "Data": {"NextFreeGift": "2026-11-10T13:00:00Z", "Rewards": [{"Quantity": 10}]},
            },
            "gift",
        )

    def test_gift_claim_still_rejects_missing_or_contradictory_cooldown(self):
        for data in [
            {},
            {"NextFreeGift": ""},
            {"NextFreeGift": True},
            {"NextFreeGift": "2026-11-10T13:00:00Z", "FreeGiftAvailable": True},
        ]:
            with self.subTest(data=data), self.assertRaises(rewards.WorkflowError):
                rewards.verify_claim({"IsSuccess": True, "Data": data}, "gift")


class ApiObservationTests(unittest.TestCase):
    def test_banner_is_clicked_once_then_waited_out_during_close_animation(self):
        state = {"visible": True, "clicks": 0}

        class Banner:
            def count(self):
                return int(state["visible"])

            def evaluate(self, expression, **kwargs):
                state["clicks"] += 1
                # A real close animation leaves the element visible briefly.

        banner = Banner()

        def locator(selector):
            return (
                banner if "communications-banner" in selector else SimpleNamespace(count=lambda: 0)
            )

        def expectation(target):
            def wait_for_count(count, **kwargs):
                self.assertIs(target, banner)
                self.assertEqual(state["clicks"], 1)
                self.assertEqual(count, 0)
                state["visible"] = False

            return SimpleNamespace(to_have_count=wait_for_count)

        workflow = rewards.DailyRewards(SimpleNamespace(locator=locator), "WonderfulFinch83")
        with patch.object(rewards, "expect", expectation):
            workflow.dismiss_popups()
        self.assertEqual(state["clicks"], 1)
        self.assertFalse(state["visible"])

    def test_modal_appearing_during_banner_dismissal_does_not_block_close(self):
        state = {"banner": True, "modal": False}
        events = []

        class CloseControl:
            def __init__(self, kind):
                self.kind = kind

            def count(self):
                if self.kind == "banner" and state["banner"]:
                    # A modal arrives after the initial backdrop check.
                    state["modal"] = True
                return int(state[self.kind])

            def click(self, **kwargs):
                raise AssertionError("Pointer close would be blocked by the arriving modal")

            def evaluate(self, expression, **kwargs):
                self_kind = self.kind
                self_test.assertIn("click()", expression)
                state[self_kind] = False
                events.append(self_kind)

        self_test = self

        class Backdrops:
            @property
            def last(self):
                return self

            def count(self):
                return int(state["modal"])

            def locator(self, selector):
                return CloseControl("modal")

        backdrops = Backdrops()

        def locator(selector):
            if selector == '[data-testid="modal-backdrop"]:visible':
                return backdrops
            if "communications-banner" in selector:
                return CloseControl("banner")
            return SimpleNamespace(count=lambda: 0)

        def assert_count(target):
            return SimpleNamespace(
                to_have_count=lambda count, **kwargs: self.assertEqual(target.count(), count)
            )

        workflow = rewards.DailyRewards(SimpleNamespace(locator=locator), "WonderfulFinch83")
        with patch.object(rewards, "expect", assert_count):
            workflow.dismiss_popups()
        self.assertEqual(events, ["banner", "modal"])
        self.assertEqual(state, {"banner": False, "modal": False})
        self.assertFalse(workflow._dismissing_popups)

    def test_scroll_closes_popups_before_and_after_moving_page(self):
        events = []

        class ScrollWorkflow(rewards.DailyRewards):
            def dismiss_popups(self):
                events.append("dismiss")

        workflow = ScrollWorkflow(None, "WonderfulFinch83")

        def evaluate(expression, **kwargs):
            self.assertEqual(events, ["dismiss"])
            self.assertIn("scrollIntoView", expression)
            self.assertEqual(kwargs["timeout"], 10000)
            events.append("scroll")

        target = SimpleNamespace(evaluate=evaluate)
        workflow.scroll_to(target, "daily wheel")
        self.assertEqual(events, ["dismiss", "scroll", "dismiss"])

    def test_readiness_wait_closes_popup_before_target_exists(self):
        class BlockedWorkflow(rewards.DailyRewards):
            closed = False

            def dismiss_popups(self):
                self.closed = True

        workflow = BlockedWorkflow(None, "WonderfulFinch83")
        wheel = SimpleNamespace(
            count=lambda: 1 if workflow.closed else 0, is_visible=lambda: workflow.closed
        )
        workflow.wait_for_ready(wheel, "wheel")
        self.assertTrue(workflow.closed)

    def test_error_summary_preserves_cause_and_removes_sensitive_urls(self):
        error = RuntimeError("Locator.click: Element is not attached to the DOM\nCall log: secret")
        self.assertEqual(
            rewards.error_summary(error),
            "RuntimeError: Locator.click: Element is not attached to the DOM",
        )
        summary = rewards.error_summary(
            RuntimeError("Failed https://example.com/path?token=secret-token")
        )
        self.assertNotIn("secret-token", summary)
        self.assertNotIn("https://", summary)

    def test_confirmation_closes_result_popup_before_waiting_for_timer(self):
        class ResultWorkflow(rewards.DailyRewards):
            closed = False

            def dismiss_popups(self):
                self.closed = True

        workflow = ResultWorkflow(None, "WonderfulFinch83")
        wheel = SimpleNamespace(
            inner_text=lambda: "Resets in 23h 59m" if workflow.closed else "SPIN"
        )
        workflow.wait_for_cooldown(wheel, r"Resets\s+in", "wheel cooldown")
        self.assertTrue(workflow.closed)

    def test_countdown_parser_handles_nested_timer_text(self):
        card = SimpleNamespace(inner_text=lambda: "Available in\n20h 42m")
        self.assertEqual(
            rewards.DailyRewards.cooldown(card, r"Available\s+in"), "Available in 20h 42m"
        )
        card.inner_text = lambda: "FREE"
        self.assertIsNone(rewards.DailyRewards.cooldown(card, r"Available\s+in"))

    def test_only_trusted_successful_api_responses_supply_availability(self):
        workflow = rewards.DailyRewards(None, "WonderfulFinch83")

        def response(host, status, payload):
            return SimpleNamespace(
                url=f"https://{host}{rewards.GIFT}",
                status=status,
                request=SimpleNamespace(method="GET"),
                json=lambda: payload,
            )

        workflow.observe(response("example.com", 200, {"IsSuccess": True, "Data": {}}))
        self.assertFalse(workflow.responses)
        workflow.observe(response("api.prod.monopolygo.com", 403, {"IsSuccess": False}))
        with self.assertRaises(rewards.WorkflowError):
            workflow.api_data(rewards.GIFT)
        workflow.observe(
            response(
                "api.prod.monopolygo.com",
                200,
                {"IsSuccess": True, "Data": {"FreeGiftAvailable": False}},
            )
        )
        self.assertEqual(workflow.api_data(rewards.GIFT), {"FreeGiftAvailable": False})

    def test_identity_failure_stops_before_any_browser_actions(self):
        workflow = rewards.DailyRewards(None, "WonderfulFinch83")
        workflow.responses[("GET", rewards.PROFILE)] = (
            200,
            {"IsSuccess": True, "Data": {"DisplayName": "OtherUser"}},
        )
        with self.assertRaises(rewards.WorkflowError):
            workflow.verify_login()


if __name__ == "__main__":
    unittest.main()
