# Licensed News And Wire-Feed Research

QUA-31 classifies newspaper and wire-feed access for low-latency automatic
ingestion. This is not legal advice; it is an engineering/licensing decision
record for V1.

## Recommendation

Do not build brittle scraping into the core platform.

The first paid feed to evaluate is LSEG News Service powered by Reuters, not a
consumer newspaper site. It is the cleanest match for the platform because it is
explicitly positioned for quantitative trading, event-based trading, market
surveillance, real-time machine delivery, topic codes, timestamps, relevance,
confidence, sentiment, significance, and deduplication.

Buy it only after the QUA-15 predictive-power dataset proves a realistic
post-cost edge from its timestamps and topic coverage. Until then:

- Use official actor feeds and exchange/company announcements as trigger-grade
  sources.
- Use E24 and DN RSS as Norwegian confirmation feeds.
- Keep NRK as context/confirmation only.
- Exclude NYT, WSJ web pages, Bloomberg web pages, FT web pages, DN pages, and
  Finansavisen pages from automated scraping.

## Feed Classification

| Source | Access path | V1 grade | Licensing/scraping risk | Notes |
| --- | --- | --- | --- | --- |
| LSEG News Service / Reuters | Paid LSEG News Service on Data Platform | Trigger-grade candidate | Low if licensed; not usable without contract | Real-time JSON via AWS Message Queue or request-response API; Reuters and third-party wires; metadata includes topic codes, UTC timestamps, relevance, confidence, sentiment, significance, and deduplication. |
| AP Media API | Paid AP Media API or AP Media Agent | Trigger-grade candidate after benchmark | Low if licensed; entitlement/contract dependent | Licensed content API supports feed/search, text stories, metadata, API keys, long polling, next-page continuation, and pricing/entitlement fields. Better as broad geopolitical coverage than Equinor-specific finance feed. |
| Bloomberg Event-Driven Feeds | Paid Bloomberg enterprise feed | Trigger-grade candidate if already contracted | Low if licensed; high cost/enterprise setup | Machine-readable real-time headlines, story bodies, metadata, and analytics; likely overkill until backtests prove paid-feed edge. |
| Dow Jones / WSJ Newswires APIs | Paid Dow Jones Developer Platform credentials | Trigger-grade candidate if licensed | Low if licensed; WSJ site scraping high risk | Newswire APIs exist behind Dow Jones credentials. Treat WSJ.com as not usable for scraping. |
| Financial Times Headline API | Licensed FT API | Confirmation/research only in V1 | Low if licensed; site scraping high risk | Headline/search API is useful for licensed headline monitoring and research, but not first trigger-grade feed for this oil shock thesis. |
| New York Times | Public API / website | Not usable for V1 automatic trading | High for commercial/AI/trading without written permission | Terms describe content as personal/non-commercial and prohibit automated scraping and AI/model use without permission. |
| E24 | Public RSS feeds | Norwegian confirmation-only | Medium; RSS is public, but full-content reuse/AI use needs care | E24 lists RSS feeds including all news and Bors og finans. Use headline/link/timestamp as confirmation; do not scrape article bodies. |
| Dagens Naeringsliv / DN | Public RSS builder | Norwegian confirmation-only | Medium; RSS terms apply; paywalled/full-content use needs permission | DN provides RSS feeds and topic/category selection. DN Investor market data is delayed and not suitable as live price source. |
| Finansavisen | No public RSS | Not usable automatically in V1 unless licensed | High without direct agreement | Finansavisen states it does not share RSS feeds; contact for paid content collaboration. |
| NRK | RSS/context feeds | Confirmation/context only | Medium-low for RSS headlines; not finance/wire grade | Useful for public Norwegian context and major geopolitical confirmation, not trigger-grade for Equinor trading. |

## Source Roles

Trigger-grade sources are allowed to open a hypothesis only when their adapter
uses an API/feed contract, preserves provenance, and can produce a valid
`RawAdapterEvent`.

V1 trigger-grade candidates:

- official US/Iran/Israel/IAEA/maritime/security feeds already in scope.
- LSEG/Reuters after paid evaluation.
- AP after paid evaluation and source-ranking benchmark.
- Bloomberg/Dow Jones only if a contract is already economically justified.

Confirmation-only sources can reinforce or confirm a hypothesis, but should not
open one by themselves:

- E24 RSS.
- DN RSS.
- NRK RSS.
- FT licensed headline/search API.

Not usable in V1 automatic ingestion:

- NYT public API or website for trading/AI workflows without written permission.
- WSJ.com, Bloomberg.com, FT.com, DN.no, Finansavisen.no page scraping.
- Finansavisen automated ingestion without a direct paid agreement.

## Paid Feed Purchase Gate

Before buying a paid newspaper/wire product, run the QUA-15 dataset against a
sample or trial feed and require all of the following:

- Measured `first_seen_at` is meaningfully earlier than official/Norwegian
  confirmation for relevant US-Iran, Hormuz, sanctions, oil supply, and shipping
  risk events.
- Source ranking beats free/official sources on post-cost directional return,
  not just raw speed.
- Coverage includes the actual oil-impact channel, especially Strait of Hormuz
  closure, tanker disruption, sanctions, military escalation, and oil supply
  disruption.
- Contract terms allow automated ingestion, storage of metadata/snippets needed
  for audit, AI analysis, and trading/research use.
- Adapter can satisfy QUA-10: raw event, normalized event, instrument reference,
  provenance, idempotency key, duplicate handling, late-event handling, and
  unsupported-event rejection.

## Implementation Notes

No core adapter should parse a paywalled HTML page. If a source does not provide
an allowed API, RSS feed, webhook, streaming endpoint, or licensed file/feed, it
does not enter automatic ingestion.

For licensed feeds, store only the fields permitted by contract. At minimum the
platform needs source id, source timestamp, first seen timestamp, headline or
licensed summary, canonical link or provider id, topic codes/tags, relevance
metadata, and audit-safe provenance.

## Sources Checked

- AP Media API overview and Feed documentation:
  https://developer.ap.org/ap-media-api/
  https://api.ap.org/media/v/docs/Feed.htm
  https://api.ap.org/media/v/docs/Getting_Started_API.htm
- LSEG News Service on Data Platform:
  https://developers.lseg.com/en/product/news/news_service_rdp
- Bloomberg Event-Driven Feeds and Enterprise API access:
  https://professional.bloomberg.com/products/data/enterprise-catalog/event-driven-feeds/
  https://console.bloomberg.com/about/1935
- Dow Jones Newswires API Postman documentation:
  https://www.postman.com/dj-cse/dow-jones-apis/documentation/238ij90/newswires-apis
- Financial Times Headline API licence documentation:
  https://www.postman.com/api-evangelist/financial-times-ft/documentation/7vluozw/headline-api-licence
- New York Times Terms of Service:
  https://thenewyorktimeshelpcenter.helpjuice.com/115002797688-Policies/115014893428-Terms-of-Service/version/2
- E24 RSS page:
  https://e24.no/boers-og-finans/i/b5jw2k/rss-feed
- DN RSS page:
  https://services.dn.no/tools/rss
- Finansavisen RSS information:
  https://www.finansavisen.no/info/rss-feed
