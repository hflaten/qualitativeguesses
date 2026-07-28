# Licensed Feed Adapter Skeletons

QUA-46 adds inert adapter skeletons for LSEG Reuters News Service and AP Media
API. They let the platform normalize trial, fixture, or vendor-supplied sample
payloads into the same `RawAdapterEvent` contract used by the rest of ingestion.

The adapters do not open live network connections yet.

## Runtime Flags

Both licensed feeds are disabled by default:

```bash
SOURCE_LSEG_REUTERS_ENABLED=false
SOURCE_AP_MEDIA_API_ENABLED=false
```

When enabled, runtime assembly exposes these adapter source IDs:

- `reuters_lseg_news`
- `ap_media_api`

The adapter `events()` streams are intentionally empty until a licensed client is
implemented. This prevents a Railway deployment from pretending to ingest paid
data before credentials, entitlements, and contract terms are in place.

## Normalized Contract

Both normalizers produce a `RawAdapterEvent` with:

- trigger-grade `source_tier`
- wire/newspaper `source_category`
- `EQNR.OL` instrument normalization for known Equinor aliases
- provider-scoped idempotency keys
- source timestamps parsed from provider timestamps
- provider provenance for audit and duplicate investigation

## Contract Gate

Before enabling live network ingestion, confirm the written vendor contract
allows all intended uses:

- automated ingestion by a continuously running service
- storage of the minimum metadata/snippets needed for audit
- AI analysis and classification
- trading research and paper-trading workflows
- future live-trading use, if that ever becomes relevant

If the contract limits storage, trim `payload["raw"]` and stored body fields to
the allowed subset before the live adapter is enabled.

## Next Implementation Step

The next step after vendor access is to add a concrete client per feed:

- LSEG Reuters: streaming API or managed queue consumer, mapped to
  `LsegReutersEventNormalizer.normalize`.
- AP Media API: feed/long-poll client, mapped to
  `ApMediaEventNormalizer.normalize`.

Both clients should reuse the raw ingestion path so malformed, duplicate, late,
and unsupported events receive the same durable treatment as existing adapters.
