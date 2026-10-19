# M7 data update (applied once with the Supabase connector, 19 Oct 2026)

Every existing `manual` check was converted in place (the old results keep their answers; their checks now
show the new rule). Steps were checked on the live site with a local browser first.

| Pair | Check (was manual) | Now | Steps |
|---|---|---|---|
| #1 browse the menu | no overlap on mobile | `ai_vision` | open `/`, click `css=summary[aria-label=Menu]` (if there) |
| #2 search Solaris | the result opens the right page | `ai_judge` (plain read) | – |
| #4 Cabinet Lights | images, prices, links for each | `ai_judge` (plain read) | – |
| #6 colour change | Sand marked, image matches | `ai_vision` | open `/products/solaris`, click `text=Sand` |
| #7 Turn On preview | lamp lit, can close | `ai_vision` | open `/products/solaris`, click `text=Turn On` |
| #8 add to cart once | (cart API checks) | `browser_count` item_count=1 and items.length=1, `ai_vision` one Solaris in Black | open `/products/solaris`, click `css=button[name=add]` |
| #9 Solaris + Walkie | options and quantities right | `ai_judge` (plain read of the cart) | – |
| #10 order summary | checkout matches the cart | `ai_vision` | open `/products/solaris`, click Add to cart, open `/checkout` (the payment page hands it to a person). Clicking "Check out" on the cart page did nothing in an automated browser (no request at all), so the step opens Shopify's `/checkout` directly |

#8's own request changed from `POST /cart/add.js` to `GET /products/solaris` (the clicks now add to the cart).
