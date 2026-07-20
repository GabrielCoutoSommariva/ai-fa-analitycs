from datetime import date, timedelta
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.modules.pop("app.services.periods", None)

from app.services.periods import parse_period  # noqa: E402


class PeriodParsingTest(unittest.TestCase):
    def test_contem_does_not_match_ontem(self):
        start = date(2026, 5, 1)
        end = date(2026, 5, 31)

        result = parse_period("Qual o valor dos cupons que contem esse item?", start, end)

        self.assertEqual(result["data_inicio"], start)
        self.assertEqual(result["data_fim"], end)

    def test_ontem_still_matches_as_word(self):
        result = parse_period("Quanto vendi ontem?", None, None)

        self.assertEqual(result["data_inicio"], date.today() - timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
