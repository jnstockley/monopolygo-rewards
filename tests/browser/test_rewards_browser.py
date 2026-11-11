"""Offline browser fixtures. RUN_BROWSER_TESTS=1 python -m unittest discover."""

import json
import unittest

from playwright.sync_api import sync_playwright

from monopolygo_rewards import rewards

HTML = """<!doctype html><html><body>
<h2 data-testid="user-name">WonderfulFinch83</h2>
<a href="/shop" aria-label="loyalty add plus button">580</a>
<nav data-testid="nav"><a href="/benefits">BENEFITS</a><a href="/shop">SHOP</a></nav>
<a href="/shop">Visit the shop</a>
<main id="main"></main><script>
const api='https://api.prod.monopolygo.com';
async function get(path) { return (await (await fetch(api+path)).json()).Data; }
function popup(onClose) {
 let p=document.createElement('div');p.dataset.testid='modal-backdrop';
 p.innerHTML='<div role="dialog">Reward</div><button data-testid="close-btn">Close modal</button>';
 p.querySelector('button').onclick=()=>{p.remove();if(onClose)onClose();};
 document.body.append(p);
}
async function render() {
 await get('/web-portal/user-profile');
 let w=await get('/web-portal/loyalty-program/v3/daily-spin');
 let g=await get('/web-portal/loyalty-program/free-gift');
 if(location.pathname==='/benefits') {
  main.innerHTML='<section data-testid="benefits-page"><h1>DAILY WHEEL</h1><div data-testid="spinner-container" data-wheel-key="'+(w.FreeSpinAvailable?'free':'paid')+'" data-wheel-points-cost="'+(w.FreeSpinAvailable?'0':'400')+'">'+
    (w.FreeSpinAvailable?'<button data-testid="spin-button">SPIN</button>':'<button data-testid="spin-button">400</button><div>Resets in 20h 43m</div>')+'</div></section>';
  if(w.FreeSpinAvailable) document.querySelector('[data-testid="spin-button"]').onclick=async()=>{
   await fetch(api+'/web-portal/loyalty-program/v2/unlock-benefit',{method:'POST',body:JSON.stringify({BenefitId:'free',BenefitType:'DailySpinV3'})});
   await render();
   const wheel=document.querySelector('[data-testid="spinner-container"]');
   const updated=wheel.innerHTML;wheel.innerHTML='<button disabled>SPIN</button>';
   popup(()=>{wheel.innerHTML=updated;});
  };
 }
 if(location.pathname==='/benefits' && window.fixtureBlockWheel) {
  const contents=main.innerHTML;main.innerHTML='';
  popup(()=>{main.innerHTML=contents;});
 }
 if(location.pathname==='/shop') {
  main.innerHTML='<div class="swiper"><button aria-label="Go to slide 2">Last</button><div style="display:flex;overflow-x:scroll;width:400px"><div style="min-width:800px"><button>$4.99</button><button>FREE unrelated offer</button></div><section data-testid="store-banners-free-gift-card" style="min-width:400px">'+
   (g.FreeGiftAvailable?'<button data-testid="free-gift-button">FREE</button>':'<div data-testid="timer-container"><p data-testid="available-text">Available in</p><div data-testid="timer-container">20h 42m</div></div>')+'</section></div></div>';
  if(g.FreeGiftAvailable) document.querySelector('[data-testid="free-gift-button"]').onclick=async()=>{
   await fetch(api+'/web-portal/loyalty-program/free-gift',{method:'POST',body:'{}'});await render();popup();
  };
 }
}
render();
</script></body></html>"""


class RewardBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception:
            cls.playwright.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.context.route("**/*", lambda route: route.abort())
        self.page = self.context.new_page()
        self.available = False
        self.claims = []
        self.fail_claim = False
        self.wrong_name = False
        self.page.route(
            "https://www.monopolygo.com/**",
            lambda route: route.fulfill(content_type="text/html", body=HTML),
        )
        self.page.route("https://api.prod.monopolygo.com/**", self.api)
        self.workflow = rewards.DailyRewards(self.page, "WonderfulFinch83")
        self.page.on("response", self.workflow.observe)
        self.workflow.install_popup_handlers()

    def tearDown(self):
        self.context.close()

    def api(self, route):
        path = route.request.url.split("monopolygo.com")[1].split("?")[0]
        data = {}
        status = 200
        if route.request.method == "POST":
            self.claims.append(path)
            status = 403 if self.fail_claim else 200
            if path == rewards.UNLOCK:
                self.wheel_claimed = True
                data = {"UnlockedBenefit": {"PointsCost": 0}}
            else:
                self.gift_claimed = True
                data = {"NextFreeGift": "2026-11-10T13:00:00Z", "Rewards": [{"Quantity": 10}]}
        elif path == rewards.PROFILE:
            data = {
                "Name": "internal-name",
                "DisplayName": "OtherUser" if self.wrong_name else "WonderfulFinch83",
            }
        elif path == rewards.WHEEL:
            available = self.available and not getattr(self, "wheel_claimed", False)
            data = {
                "FreeSpinAvailable": available,
                "Wheels": [{"Key": "free", "PointsCost": 0, "Available": available}],
            }
        elif path == rewards.GIFT:
            data = {
                "FreeGiftDefined": True,
                "FreeGiftAvailable": self.available and not getattr(self, "gift_claimed", False),
            }
        route.fulfill(
            status=status,
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"},
            body=json.dumps({"IsSuccess": status == 200, "Data": data}),
        )

    def start(self):
        self.page.goto("https://www.monopolygo.com/news")

    def test_cooldowns_skip_both_without_claims(self):
        self.start()
        results = self.workflow.run()
        self.assertEqual([r.status for r in results.results], ["skipped", "skipped"])
        self.assertEqual(self.claims, [])

    def test_only_two_available_daily_rewards_are_claimed(self):
        self.available = True
        self.start()
        results = self.workflow.run()
        self.assertEqual([r.status for r in results.results], ["claimed", "claimed"])
        self.assertEqual(self.claims, [rewards.UNLOCK, rewards.GIFT])
        self.assertEqual(self.page.get_by_test_id("modal-backdrop").count(), 0)

    def test_wrong_username_prevents_all_claims(self):
        self.available = True
        self.wrong_name = True
        self.start()
        with self.assertRaises(rewards.WorkflowError):
            self.workflow.run()
        self.assertEqual(self.claims, [])

    def test_failed_claim_is_not_retried_and_shop_is_not_claimed(self):
        self.available = True
        self.fail_claim = True
        self.start()
        with self.assertRaises(rewards.WorkflowError):
            self.workflow.run()
        self.assertEqual(self.claims, [rewards.UNLOCK])

    def test_unknown_blocking_popup_stops_before_claims(self):
        self.start()
        self.page.evaluate(
            "document.body.insertAdjacentHTML('beforeend','<div role=dialog>Unknown</div>')"
        )
        with self.assertRaises(rewards.WorkflowError):
            self.workflow.run()
        self.assertEqual(self.claims, [])

    def test_popup_appearing_between_checks_is_closed_before_action(self):
        self.start()
        self.page.evaluate("popup()")
        # Deliberately bypass manual dismissal to exercise the action-time handler.
        self.page.get_by_role("link", name="BENEFITS", exact=True).click()
        self.assertEqual(self.page.get_by_test_id("modal-backdrop").count(), 0)
        self.assertEqual(self.claims, [])

    def test_popup_is_closed_when_it_prevents_wheel_from_rendering(self):
        self.page.add_init_script("window.fixtureBlockWheel=true;")
        self.start()
        results = self.workflow.run()
        self.assertEqual([r.status for r in results.results], ["skipped", "skipped"])
        self.assertEqual(self.claims, [])

    def test_delayed_prior_response_cannot_confirm_new_failed_claim(self):
        self.page.set_content(
            """<button id="claim" onclick="fetch('https://api.prod.monopolygo.com/web-portal/loyalty-program/v2/unlock-benefit',{method:'POST',body:'current'}).catch(()=>{})">claim</button>"""
        )
        held = []

        def unlock(route):
            headers = {"Access-Control-Allow-Origin": "*"}
            if route.request.post_data == "earlier":
                held.append(route)
            else:

                def release_current(response):
                    if response.request.post_data == "earlier":
                        self.page.remove_listener("response", release_current)
                        route.fulfill(
                            status=403,
                            content_type="application/json",
                            headers=headers,
                            body=json.dumps({"IsSuccess": False}),
                        )

                self.page.on("response", release_current)
                held[0].fulfill(
                    status=200,
                    content_type="application/json",
                    headers=headers,
                    body=json.dumps(
                        {"IsSuccess": True, "Data": {"UnlockedBenefit": {"PointsCost": 0}}}
                    ),
                )

        self.page.route("https://api.prod.monopolygo.com" + rewards.UNLOCK, unlock)
        with self.page.expect_request(
            lambda request: request.method == "POST" and request.post_data == "earlier"
        ):
            self.page.evaluate(
                "() => { void fetch('https://api.prod.monopolygo.com/web-portal/loyalty-program/v2/unlock-benefit',{method:'POST',body:'earlier'}).catch(()=>{}); }"
            )
        with self.assertRaises(rewards.WorkflowError):
            self.workflow.claim(self.page.locator("#claim"), rewards.UNLOCK, "wheel")
