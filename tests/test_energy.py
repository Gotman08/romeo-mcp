"""Mesures Slurm, perimetres carbone, trous et facteurs absents : sans cluster."""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from romeo_mcp import carbon, energy, hardware

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(hours=1)


def runner(joules="3600000", exclusive="yes", plugin="acct_gather_energy/ipmi", state="COMPLETED"):
    def read(command, **kwargs):
        if "--helpformat" in command:
            return SimpleNamespace(ok=True, stdout="JobID Exclusive ConsumedEnergyRaw")
        if "Exclusive" in command:
            return SimpleNamespace(ok=True, stdout=f"123|{exclusive}|")
        if "scontrol" in command:
            return SimpleNamespace(ok=True, stdout=f"AcctGatherEnergyType = {plugin}")
        return SimpleNamespace(ok=True, stdout=f"123|{state}|3600|8|cpu=8|{joules}|2026-01-01T00:00:00|2026-01-01T01:00:00|")
    return Mock(side_effect=read)


class EnergyTests(unittest.TestCase):
    def test_joules_conversion_and_observed_factor_are_not_co2_measurements(self):
        factor = Mock(return_value={"intensity_g_kwh": 31, "source": "fixture", "coverage": 1})
        result = energy.footprint("123", runner(), carbon_lookup=factor)
        self.assertEqual(result["energie_kwh"], 1)
        self.assertEqual(result["co2e_g"], 31)
        self.assertTrue(result["mesure_reelle"])
        self.assertFalse(result["co2_measured"])
        self.assertEqual(result["carbon"]["status"], "estimated")
        factor.assert_called_once_with(START, END)

    def test_zero_missing_counter_and_disabled_plugin_never_become_a_zero_measurement(self):
        for raw in ("0", "", "Unknown", "-1", "NaN"):
            factor = Mock()
            result = energy.footprint("123", runner(raw, plugin="(null)"), carbon_lookup=factor)
            self.assertIsNone(result["energie_kwh"])
            self.assertIsNone(result["co2e_g"])
            self.assertFalse(result["mesure_reelle"])
            self.assertFalse(result["measurement"]["energy_plugin_enabled_now"])
            self.assertNotIn("estimate", result)
            factor.assert_not_called()

    def test_shared_or_unknown_allocation_is_not_attributed_to_the_job(self):
        for exclusive in ("no", "unknown"):
            result = energy.footprint("123", runner(exclusive=exclusive), carbon_source="none")
            self.assertIsNone(result["energie_kwh"])
            self.assertEqual(result["measurement"]["allocation_energy_kwh"], 1)
            self.assertFalse(result["mesure_reelle"])

    def test_old_slurm_without_exclusive_field_does_not_claim_a_job_measurement(self):
        original = runner()
        def read(command, **kwargs):
            if "--helpformat" in command:
                return SimpleNamespace(ok=True, stdout="JobID ConsumedEnergyRaw")
            return original(command, **kwargs)
        result = energy.footprint("123", read, carbon_source="none")
        self.assertIsNone(result["measurement"]["exclusive_allocation"])
        self.assertIsNone(result["energie_kwh"])

    def test_optional_estimate_is_separate_and_factor_failure_has_no_constant_fallback(self):
        lookup = Mock(side_effect=carbon.CarbonUnavailable("missing"))
        result = energy.footprint("123", runner("0"), estimate=True, carbon_lookup=lookup)
        self.assertIsNone(result["energie_kwh"])
        self.assertGreater(result["estimate"]["energie_kwh"], 0)
        self.assertIsNone(result["estimate"]["co2e_g"])
        self.assertFalse(result["mesure_reelle"])
        self.assertEqual(result["carbon"]["status"], "unavailable")

    def test_invalid_options_and_selectors_do_not_read_ssh(self):
        for kwargs in ({"gpu_load_factor": float("nan")}, {"gpu_load_factor": 2},
                       {"carbon_source": "manual", "carbon_intensity": 56},
                       {"carbon_source": "manual", "carbon_intensity": -1, "carbon_reference": "fixture"},
                       {"carbon_intensity": 56}, {"estimate": "yes"}):
            read = Mock()
            with self.assertRaises(ValueError):
                energy.footprint("123", read, **kwargs)
            read.assert_not_called()
        for job in ("123.batch", "123,456", "--help", "123;hostname", "0", "123\n"):
            with self.assertRaises(ValueError):
                energy.footprint(job, Mock())

    def test_optional_model_keeps_carbon_intensity_and_band_consistent(self):
        factor = Mock(return_value={"intensity_g_kwh": 25, "source": "fixture", "coverage": 1})
        result = energy.footprint("123", runner("0"), estimate=True, carbon_lookup=factor)
        model = result["estimate"]
        self.assertIsNone(result["co2e_g"])
        self.assertEqual(model["intensite_carbone_g_kwh"], 25)
        self.assertEqual(model["co2e_g_fourchette"], [value * 25 for value in model["energie_kwh_fourchette"]])
        self.assertEqual(result["carbon"]["co2e_g"], model["co2e_g"])

    def test_accounting_is_exact_and_steps_are_not_double_counted(self):
        text = "1234|COMPLETED|3600|1|cpu=1|10|Unknown|Unknown|\n123.batch|COMPLETED|3600|1|cpu=1|20|Unknown|Unknown|"
        with self.assertRaises(ValueError):
            energy.parse_accounting(text, "123")
        duplicate = "123|COMPLETED|0|1|cpu=1|0|Unknown|Unknown|\n" * 2
        with self.assertRaises(ValueError):
            energy.parse_accounting(duplicate, "123")

    def test_manual_factor_is_explicit_unverified_and_reference_is_required(self):
        result = energy.footprint("123", runner(), carbon_source="manual", carbon_intensity=25,
                                  carbon_reference="Fixture 2026-01 : emissions directes")
        self.assertEqual(result["co2e_g"], 25)
        self.assertFalse(result["carbon"]["verified"])

    def test_small_counter_is_not_rounded_to_zero(self):
        result = energy.footprint("123", runner("1"), carbon_source="none")
        self.assertGreater(result["energie_kwh"], 0)
        self.assertAlmostEqual(result["energie_kwh"], 1 / 3_600_000)

    def test_model_has_no_implicit_carbon_and_band_contains_low_high_assumptions(self):
        for factor in (0.1, 1):
            model = hardware.estimer_energie(1, 1, 3600, facteur_charge=factor)
            low, high = model["energie_kwh_fourchette"]
            self.assertLessEqual(low, model["energie_kwh"])
            self.assertGreaterEqual(high, model["energie_kwh"])
            self.assertIsNone(model["co2e_g"])
        with self.assertRaises(ValueError):
            hardware.estimer_energie(1, 1, float("nan"))


class CarbonTests(unittest.TestCase):
    def rows(self, *values):
        return [{"date_heure": (START + timedelta(minutes=30*i)).isoformat(), "taux_co2": value}
                for i, value in enumerate(values)]

    def test_partial_slots_are_time_weighted(self):
        result = carbon.weighted_factor(self.rows(10, 30), START+timedelta(minutes=15), END, 1800)
        self.assertAlmostEqual(result["intensity_g_kwh"], (10*15+30*30)/45)
        self.assertEqual(result["coverage"], 1)

    def test_missing_null_invalid_and_conflicting_slots_are_not_filled(self):
        cases = (self.rows(10), self.rows(10, None), self.rows(10, -1),
                 self.rows(10, 30) + self.rows(20))
        for rows in cases:
            with self.assertRaises(carbon.CarbonUnavailable):
                carbon.weighted_factor(rows, START, END, 1800)

    def test_falls_back_to_realtime_only_with_full_coverage_and_no_current_factor(self):
        rows = [{"date_heure": (START+timedelta(minutes=15*i)).isoformat(), "taux_co2": 12} for i in range(4)]
        with patch.object(carbon, "_records", side_effect=[[], rows]) as read:
            result = carbon.rte_factor(START, END)
        self.assertEqual(result["dataset"], "eco2mix-national-tr")
        self.assertEqual(result["intensity_g_kwh"], 12)
        self.assertEqual(read.call_count, 2)

    def test_http_is_bounded_no_redirect_and_contains_no_job_identifier(self):
        response = io.BytesIO(json.dumps({"total_count": 2, "results": self.rows(10, 30)}).encode())
        response.status = 200
        opener = Mock()
        opener.open.return_value = response
        with patch.object(carbon, "build_opener", return_value=opener) as factory:
            result = carbon.rte_factor(START, END)
        request = opener.open.call_args.args[0]
        self.assertTrue(request.full_url.startswith(carbon.API_ROOT))
        self.assertNotIn("job", request.full_url)
        params = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(params["where"], [
            'date_heure >= "2025-12-31T23:30:00+00:00" and date_heure < "2026-01-01T01:00:00+00:00"'])
        self.assertIsInstance(factory.call_args.args[0], carbon.NoRedirect)
        self.assertEqual(result["coverage"], 1)


if __name__ == "__main__":
    unittest.main()
