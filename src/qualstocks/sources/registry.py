from __future__ import annotations

from dataclasses import dataclass

from qualstocks.domain import (
    AccessMethod,
    LicensingClass,
    SourceCategory,
    SourceClass,
    SourceTier,
)


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    name: str
    source_class: SourceClass
    tier: SourceTier
    category: SourceCategory
    access_methods: tuple[AccessMethod, ...]
    reliability_score: float
    expected_latency_seconds: int | None
    licensing_class: LicensingClass
    language: str
    translation_required: bool = False
    url: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must be non-empty")
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if not self.access_methods:
            raise ValueError("at least one access method is required")
        if not 0 <= self.reliability_score <= 1:
            raise ValueError("reliability_score must be between 0 and 1")
        if self.expected_latency_seconds is not None and self.expected_latency_seconds < 0:
            raise ValueError("expected_latency_seconds cannot be negative")

    @property
    def is_trigger_grade(self) -> bool:
        return self.tier == SourceTier.TRIGGER

    @property
    def is_confirmation_source(self) -> bool:
        return self.tier == SourceTier.CONFIRMATION

    @property
    def is_control_signal(self) -> bool:
        return self.tier == SourceTier.CONTROL


class SourceRegistry:
    def __init__(self, sources: tuple[SourceDefinition, ...]) -> None:
        by_id: dict[str, SourceDefinition] = {}
        for source in sources:
            if source.source_id in by_id:
                raise ValueError(f"duplicate source_id: {source.source_id}")
            by_id[source.source_id] = source
        self._by_id = by_id

    def get(self, source_id: str) -> SourceDefinition | None:
        return self._by_id.get(source_id)

    def require(self, source_id: str) -> SourceDefinition:
        source = self.get(source_id)
        if source is None:
            raise KeyError(f"unknown source_id: {source_id}")
        return source

    def all(self) -> tuple[SourceDefinition, ...]:
        return tuple(self._by_id.values())

    def ids(self) -> tuple[str, ...]:
        return tuple(self._by_id)

    def by_tier(self, tier: SourceTier) -> tuple[SourceDefinition, ...]:
        return tuple(source for source in self._by_id.values() if source.tier == tier)

    def by_category(self, category: SourceCategory) -> tuple[SourceDefinition, ...]:
        return tuple(source for source in self._by_id.values() if source.category == category)


DEFAULT_SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_id="polymarket",
        name="Polymarket",
        source_class=SourceClass.PREDICTION_MARKET,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.PREDICTION_MARKET,
        access_methods=(AccessMethod.REST_API, AccessMethod.WEBSOCKET),
        reliability_score=0.82,
        expected_latency_seconds=2,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        url="https://docs.polymarket.com/market-data/realtime-data",
        notes="Primary V1 probability-shock trigger for war, oil, and Hormuz markets.",
    ),
    SourceDefinition(
        source_id="kalshi",
        name="Kalshi",
        source_class=SourceClass.PREDICTION_MARKET,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.PREDICTION_MARKET,
        access_methods=(AccessMethod.REST_API, AccessMethod.WEBSOCKET),
        reliability_score=0.8,
        expected_latency_seconds=3,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        url="https://docs.kalshi.com/welcome",
        notes="Prediction-market confirmation; live WebSocket requires signed API auth.",
    ),
    SourceDefinition(
        source_id="dod_rss",
        name="U.S. Department of Defense RSS",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_US,
        access_methods=(AccessMethod.RSS,),
        reliability_score=0.9,
        expected_latency_seconds=60,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        url="https://www.defense.gov/news/rss",
    ),
    SourceDefinition(
        source_id="centcom_rss",
        name="CENTCOM RSS",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_US,
        access_methods=(AccessMethod.RSS,),
        reliability_score=0.92,
        expected_latency_seconds=60,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        url="https://www.centcom.mil/rss/",
    ),
    SourceDefinition(
        source_id="white_house_news",
        name="White House News",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_US,
        access_methods=(AccessMethod.OFFICIAL_PAGE,),
        reliability_score=0.9,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        url="https://www.whitehouse.gov/news/",
    ),
    SourceDefinition(
        source_id="state_department",
        name="U.S. State Department",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_US,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.88,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        url="https://www.state.gov/",
    ),
    SourceDefinition(
        source_id="irna",
        name="IRNA",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_IRAN,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.78,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="fa",
        translation_required=True,
        url="https://www.irna.ir/",
        notes="Official Iran state source; preserve state-bias metadata.",
    ),
    SourceDefinition(
        source_id="iran_foreign_ministry",
        name="Iranian Foreign Ministry",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_IRAN,
        access_methods=(AccessMethod.OFFICIAL_PAGE,),
        reliability_score=0.86,
        expected_latency_seconds=180,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="fa",
        translation_required=True,
    ),
    SourceDefinition(
        source_id="tasnim",
        name="Tasnim News Agency",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_IRAN,
        access_methods=(AccessMethod.RSS,),
        reliability_score=0.74,
        expected_latency_seconds=90,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="fa",
        translation_required=True,
        url="https://www.tasnimnews.ir/fa/rss",
    ),
    SourceDefinition(
        source_id="mehr",
        name="Mehr News Agency",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_IRAN,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.72,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="fa",
        translation_required=True,
    ),
    SourceDefinition(
        source_id="fars",
        name="Fars News Agency",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_IRAN,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.72,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="fa",
        translation_required=True,
    ),
    SourceDefinition(
        source_id="presstv",
        name="PressTV",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.OFFICIAL_IRAN,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.68,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
    ),
    SourceDefinition(
        source_id="euronext_newsweb",
        name="Oslo Bors / Euronext NewsWeb",
        source_class=SourceClass.EQUINOR_OR_EXCHANGE,
        tier=SourceTier.CONFIRMATION,
        category=SourceCategory.NORWEGIAN_MARKET,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.95,
        expected_latency_seconds=60,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        notes="Primary borsmelding/market-disclosure source and exit-timer anchor.",
    ),
    SourceDefinition(
        source_id="equinor_ir",
        name="Equinor Investor Relations",
        source_class=SourceClass.EQUINOR_OR_EXCHANGE,
        tier=SourceTier.CONFIRMATION,
        category=SourceCategory.NORWEGIAN_MARKET,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.94,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
    ),
    SourceDefinition(
        source_id="e24",
        name="E24",
        source_class=SourceClass.NORWEGIAN_CONFIRMATION,
        tier=SourceTier.CONFIRMATION,
        category=SourceCategory.NORWEGIAN_PRESS,
        access_methods=(AccessMethod.RSS, AccessMethod.PAID_API),
        reliability_score=0.76,
        expected_latency_seconds=180,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="no",
        translation_required=True,
    ),
    SourceDefinition(
        source_id="dn",
        name="Dagens Naeringsliv",
        source_class=SourceClass.NORWEGIAN_CONFIRMATION,
        tier=SourceTier.CONFIRMATION,
        category=SourceCategory.NORWEGIAN_PRESS,
        access_methods=(AccessMethod.RSS, AccessMethod.PAID_API),
        reliability_score=0.76,
        expected_latency_seconds=180,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="no",
        translation_required=True,
    ),
    SourceDefinition(
        source_id="ap_media_api",
        name="AP Media API",
        source_class=SourceClass.OSINT,
        tier=SourceTier.CONFIRMATION,
        category=SourceCategory.WIRE_OR_NEWSPAPER,
        access_methods=(AccessMethod.PAID_API,),
        reliability_score=0.86,
        expected_latency_seconds=30,
        licensing_class=LicensingClass.PAID_LICENSE_REQUIRED,
        language="en",
        url="https://api.ap.org/media/v/docs/Getting_Started_API.htm",
    ),
    SourceDefinition(
        source_id="reuters_lseg_news",
        name="Reuters / LSEG News Service",
        source_class=SourceClass.OSINT,
        tier=SourceTier.CONFIRMATION,
        category=SourceCategory.WIRE_OR_NEWSPAPER,
        access_methods=(AccessMethod.PAID_API, AccessMethod.STREAMING_API),
        reliability_score=0.9,
        expected_latency_seconds=10,
        licensing_class=LicensingClass.PAID_LICENSE_REQUIRED,
        language="en",
        url="https://developers.lseg.com/en/product/news/news_service_rdp",
    ),
    SourceDefinition(
        source_id="ukmto",
        name="UKMTO Warnings and Advisories",
        source_class=SourceClass.OSINT,
        tier=SourceTier.TRIGGER,
        category=SourceCategory.MARITIME_SECURITY,
        access_methods=(AccessMethod.OFFICIAL_PAGE, AccessMethod.EMAIL_ALERT),
        reliability_score=0.9,
        expected_latency_seconds=120,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        url="https://www.ukmto.org/ukmto-products",
        notes="Trigger-grade for Gulf/Hormuz maritime security events.",
    ),
    SourceDefinition(
        source_id="marinetraffic",
        name="MarineTraffic AIS API",
        source_class=SourceClass.MARKET_CONTROL,
        tier=SourceTier.CONTROL,
        category=SourceCategory.AIS_TANKER_FLOW,
        access_methods=(AccessMethod.PAID_API,),
        reliability_score=0.82,
        expected_latency_seconds=60,
        licensing_class=LicensingClass.PAID_LICENSE_REQUIRED,
        language="en",
        url="https://servicedocs.marinetraffic.com/",
    ),
    SourceDefinition(
        source_id="vortexa",
        name="Vortexa Tanker Tracking",
        source_class=SourceClass.MARKET_CONTROL,
        tier=SourceTier.CONTROL,
        category=SourceCategory.AIS_TANKER_FLOW,
        access_methods=(AccessMethod.PAID_API,),
        reliability_score=0.86,
        expected_latency_seconds=300,
        licensing_class=LicensingClass.PAID_LICENSE_REQUIRED,
        language="en",
        notes="Used by EIA in chokepoint analysis; evaluate commercial access.",
    ),
    SourceDefinition(
        source_id="brent_wti",
        name="Brent / WTI",
        source_class=SourceClass.MARKET_CONTROL,
        tier=SourceTier.CONTROL,
        category=SourceCategory.ENERGY_MARKET,
        access_methods=(AccessMethod.STREAMING_API, AccessMethod.PAID_API),
        reliability_score=0.88,
        expected_latency_seconds=5,
        licensing_class=LicensingClass.PAID_LICENSE_REQUIRED,
        language="en",
    ),
    SourceDefinition(
        source_id="usd_nok",
        name="USD/NOK",
        source_class=SourceClass.MARKET_CONTROL,
        tier=SourceTier.CONTROL,
        category=SourceCategory.MACRO_FX,
        access_methods=(AccessMethod.STREAMING_API, AccessMethod.PAID_API),
        reliability_score=0.82,
        expected_latency_seconds=5,
        licensing_class=LicensingClass.PAID_LICENSE_REQUIRED,
        language="en",
    ),
    SourceDefinition(
        source_id="gdelt",
        name="GDELT",
        source_class=SourceClass.OSINT,
        tier=SourceTier.CONTROL,
        category=SourceCategory.OSINT_AGGREGATE,
        access_methods=(AccessMethod.REST_API,),
        reliability_score=0.65,
        expected_latency_seconds=900,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="multi",
        translation_required=True,
        notes="Media acceleration and multilingual clustering; not a direct trigger alone.",
    ),
    SourceDefinition(
        source_id="iaea",
        name="IAEA",
        source_class=SourceClass.OFFICIAL_ACTOR,
        tier=SourceTier.CONTROL,
        category=SourceCategory.OFFICIAL_US,
        access_methods=(AccessMethod.RSS, AccessMethod.OFFICIAL_PAGE),
        reliability_score=0.88,
        expected_latency_seconds=300,
        licensing_class=LicensingClass.PUBLIC_WITH_TERMS,
        language="en",
        notes="Nuclear escalation context; usually reinforces or suppresses a thesis.",
    ),
)

DEFAULT_SOURCE_REGISTRY = SourceRegistry(DEFAULT_SOURCE_DEFINITIONS)
