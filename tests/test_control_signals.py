from __future__ import annotations

import unittest

from qualstocks.domain import (
    ActiveHypothesis,
    Direction,
    HypothesisState,
    SourceCategory,
    SourceTier,
)
from qualstocks.signals import (
    ControlSignalEffect,
    HormuzClosureSignal,
    HormuzClosureState,
    decide_control_signal_effect,
)
from qualstocks.sources import (
    ControlSignalAction,
    ControlSignalKind,
    ControlSignalNormalizer,
    ControlSignalSnapshot,
    ais_tanker_flow_event,
    energy_market_event,
    gdelt_media_acceleration_event,
    iaea_nuclear_escalation_event,
    macro_fx_event,
    ukmto_alert_event,
)


class ControlSignalTest(unittest.TestCase):
    def test_ukmto_alert_is_trigger_grade_maritime_control_input(self):
        event = ukmto_alert_event(
            title="UKMTO warning: incident near Strait of Hormuz",
            url="https://example.invalid/ukmto",
            summary="Vessel reported attack near Hormuz.",
            confidence=0.8,
            raw_event_ref="ukmto-1",
        )

        self.assertEqual(event.source_id, "ukmto")
        self.assertEqual(event.source_tier, SourceTier.TRIGGER)
        self.assertEqual(event.source_category, SourceCategory.MARITIME_SECURITY)
        self.assertEqual(event.payload["control_signal_kind"], ControlSignalKind.MARITIME_ALERT)
        self.assertEqual(event.payload["control_signal_action"], ControlSignalAction.STRENGTHEN)

    def test_ais_tanker_flow_event_feeds_hormuz_composite(self):
        event = ais_tanker_flow_event(
            source_id="marinetraffic",
            title="AIS update for Strait of Hormuz",
            url="https://example.invalid/ais",
            transit_drop_pct=-0.42,
            queue_count=12,
            raw_event_ref="ais-1",
        )

        assessment = HormuzClosureSignal().assess((event,))

        self.assertEqual(event.source_tier, SourceTier.CONTROL)
        self.assertEqual(event.source_category, SourceCategory.AIS_TANKER_FLOW)
        self.assertEqual(assessment.state, HormuzClosureState.DEGRADED)
        self.assertTrue(assessment.is_actionable)

    def test_oil_and_fx_events_are_control_metadata_not_standalone_hypotheses(self):
        oil_event = energy_market_event(
            title="Brent and WTI jump after Gulf headlines",
            url="https://example.invalid/oil",
            brent_move_pct=5.4,
            wti_move_pct=4.8,
            raw_event_ref="oil-1",
        )
        fx_event = macro_fx_event(
            title="USD/NOK spikes during oil shock",
            url="https://example.invalid/fx",
            usd_nok_move_pct=1.2,
            raw_event_ref="fx-1",
        )

        oil_decision = decide_control_signal_effect(oil_event, active_hypothesis=None)
        fx_decision = decide_control_signal_effect(fx_event, active_hypothesis=None)

        self.assertEqual(oil_event.source_tier, SourceTier.CONTROL)
        self.assertEqual(fx_event.source_tier, SourceTier.CONTROL)
        self.assertEqual(oil_decision.effect, ControlSignalEffect.ANNOTATE_ONLY)
        self.assertFalse(oil_decision.opens_new_hypothesis)
        self.assertEqual(fx_decision.effect, ControlSignalEffect.ANNOTATE_ONLY)
        self.assertFalse(fx_decision.opens_new_hypothesis)

    def test_control_signal_can_strengthen_active_hypothesis(self):
        active = ActiveHypothesis(
            thesis="Hormuz disruption should raise Equinor through oil repricing.",
            direction=Direction.BULLISH_EQUINOR,
            confidence=0.7,
            state=HypothesisState.ACTIVE,
            source_event_ids=("event-1",),
        )
        event = ais_tanker_flow_event(
            source_id="vortexa",
            title="Tanker flow through Hormuz falls sharply",
            url="https://example.invalid/vortexa",
            transit_drop_pct=-0.52,
            raw_event_ref="vortexa-1",
        )

        decision = decide_control_signal_effect(event, active_hypothesis=active)

        self.assertEqual(decision.effect, ControlSignalEffect.STRENGTHEN_ACTIVE)
        self.assertFalse(decision.opens_new_hypothesis)

    def test_gdelt_and_iaea_placeholders_normalize_as_control_events(self):
        gdelt = gdelt_media_acceleration_event(
            title="GDELT acceleration for Iran Hormuz articles",
            url="https://example.invalid/gdelt",
            article_count=120,
            acceleration_ratio=3.2,
            raw_event_ref="gdelt-1",
        )
        iaea = iaea_nuclear_escalation_event(
            title="IAEA statement on Iran nuclear inspections",
            url="https://example.invalid/iaea",
            summary="IAEA says monitoring conditions changed.",
            confidence=0.72,
            raw_event_ref="iaea-1",
        )

        self.assertEqual(gdelt.payload["control_signal_kind"], "media_acceleration")
        self.assertEqual(iaea.payload["control_signal_kind"], "nuclear_escalation")
        self.assertEqual(gdelt.source_tier, SourceTier.CONTROL)
        self.assertEqual(iaea.source_tier, SourceTier.CONTROL)

    def test_control_snapshot_validates_confidence_bounds(self):
        with self.assertRaises(ValueError):
            ControlSignalSnapshot(
                source_id="gdelt",
                kind=ControlSignalKind.MEDIA_ACCELERATION,
                title="Bad confidence",
                url="https://example.invalid",
                summary="bad",
                confidence=1.5,
            )

    def test_normalizer_preserves_raw_metrics(self):
        event = ControlSignalNormalizer().normalize(
            ControlSignalSnapshot(
                source_id="gdelt",
                kind=ControlSignalKind.MEDIA_ACCELERATION,
                title="GDELT Iran acceleration",
                url="https://example.invalid/gdelt",
                summary="Large increase in Iran/Hormuz coverage.",
                confidence=0.65,
                metrics={"article_count": 50},
                raw_event_ref="gdelt-2",
            )
        )

        self.assertEqual(event.payload["article_count"], 50)
        self.assertEqual(event.raw_event_ref, "gdelt-2")


if __name__ == "__main__":
    unittest.main()
