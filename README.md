# CAN/BUILD

A Canadian PC parts price watch created by **Jims2333 in collaboration with ChatGPT**. [Open the dashboard](https://jims2333.github.io/canbuild-watch/).

## Using the dashboard

Choose a CPU bundle, graphics card and SSD to compare the total against a budget in Canadian dollars. The planner applies 13% Ontario HST and excludes shipping and rebates. A missing GPU price leaves the total blank. The manual RTX 4070 Ti SUPER option lets you enter a retailer quote.

Each parts row links to its source. Compare price observations over 30, 90 or 365 days. A GPU family curve can switch models between dates. Export a JSON snapshot to carry a build between browsers, or edit a price for the current browser.

## How updates work

GitHub Actions runs the Python collector at minute 17 of every second UTC hour. GitHub may delay scheduled runs. Requests retrieves public pages. Beautiful Soup extracts offers from PC Tech Vault and Canadian retailer pages. When the tracker is unavailable, the collector checks selected Canada Computers SKUs and new, orderable RTX 4070 Ti SUPER listings on Newegg Canada. GPU family prices cover the listings the collector could verify. The retailer link identifies the model or marketplace listing. A separate PNY RTX 4070 Ti SUPER option monitors the listed CAD price and stock at DeployDepot, including when sold out. Successful checks update the snapshot and up to 365 daily observations per tracked part. A failed check preserves the previous observation and its date. The dashboard shows reference prices when a source has never produced a quote.

HTML, CSS, JavaScript and SVG render the planner and history chart. GitHub Pages serves the dashboard and its JSON feed. The browser refresh button reads the latest published snapshot. The feed header uses Toronto time. Individual observation timestamps are labeled UTC.

## Release verification

Each release runs eight parser fixtures with Python unittest, then opens the built site in Chromium with Playwright. The browser checks the feed, English interface, budget calculation, missing quote, reset, history link, JSON export/import, refresh and mobile width.

[Latest verification results](https://jims2333.github.io/canbuild-watch/verification/checks.json) · [Desktop screenshot](https://jims2333.github.io/canbuild-watch/verification/desktop.png) · [Budget test screenshot](https://jims2333.github.io/canbuild-watch/verification/budget.png) · [Mobile screenshot](https://jims2333.github.io/canbuild-watch/verification/mobile.png) · [Workflow runs](https://github.com/Jims2333/canbuild-watch/actions)

The budget screenshot uses a CAD 1,000 manual GPU quote as a test input. The desktop and mobile screenshots show the default build from that release. Retailer stock and checkout prices can change after an observation.


## Build finder

Open [Find a build](https://jims2333.github.io/canbuild-watch/#recommendations). The default target is CA$3,000 after Ontario HST with a 10% range. Choose a workload or any of eight component categories. Each result represents a distinct CPU and GPU family. Open **Parts & offers** for retailer pages, dates and stock in the planner, or **Use build** to edit the configuration. Exact filters can return fewer than ten results.

The finder checks CPU socket and memory generation, reserves a dual-tower cooler for higher-power processors, and uses at least 850W for an RTX 5080. It checks matching three-part bundle offers alongside standalone prices. Within the chosen price range it ranks complete offers by availability, then budget distance with a preference for 32GB or more and fewer unconfirmed quotes. Reference offers carry their November 23, 2026 date. Shipping is extra.

The HTML catalogue drives both the JavaScript finder and the Python / Beautiful Soup price collector. GitHub Actions runs parser tests and Playwright in Chromium, publishes desktop and mobile screenshots, and deploys the resulting site to GitHub Pages. The scheduled collector retains the last observation and its timestamp when a retailer check fails.

[Finder screenshot](https://jims2333.github.io/canbuild-watch/verification/recommendations.png) · [Mobile filters](https://jims2333.github.io/canbuild-watch/verification/filters-mobile.png) · [Test results](https://jims2333.github.io/canbuild-watch/verification/checks.json)
