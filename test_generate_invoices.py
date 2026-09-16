#!/usr/bin/env python3
"""Smoke tests for invoice generation (stdlib unittest, no extra deps)."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from generate_invoices import generate_invoices, load_invoices, normalize_currency


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "invoice_data_100.csv"
SAMPLE_CSV_PATH = ROOT / "data" / "invoice_sample_data.csv"


class InvoiceGeneratorTests(unittest.TestCase):
    def test_csv_loads_100_invoices(self) -> None:
        invoices = load_invoices(CSV_PATH)
        self.assertEqual(len(invoices), 100)
        self.assertTrue(all(inv.number for inv in invoices))
        self.assertTrue(all(inv.currency in {"$", "€", "₱", "¥"} for inv in invoices))

    def test_currency_aliases(self) -> None:
        self.assertEqual(normalize_currency("?"), "₱")
        self.assertEqual(normalize_currency("￥"), "¥")
        self.assertEqual(normalize_currency("EUR"), "€")

    def test_generate_limit_and_tax_row(self) -> None:
        invoices = load_invoices(CSV_PATH)
        taxed = next(inv for inv in invoices if inv.tax is not None)
        with tempfile.TemporaryDirectory() as tmp:
            written = generate_invoices(CSV_PATH, Path(tmp), limit=3)
            self.assertEqual(len(written), 3)
            for path in written:
                data = path.read_bytes()
                self.assertTrue(data.startswith(b"%PDF"))
                self.assertGreater(len(data), 2000)
                self.assertIn(b"/Image", data)
            third = Path(tmp) / f"Invoice-{invoices[2].number}.pdf"
            self.assertTrue(third.exists())
            self.assertEqual(invoices[2].number, taxed.number)


    def test_dual_currency_sample_csv(self) -> None:
        invoices = load_invoices(SAMPLE_CSV_PATH)
        self.assertEqual(len(invoices), 100)
        first = invoices[0]
        self.assertEqual(first.number, "JWNN4UKF-0001")
        self.assertEqual(first.currency, "¥")
        self.assertEqual(first.quantity, "9")
        self.assertEqual(first.amount_due, Decimal("14040"))
        with tempfile.TemporaryDirectory() as tmp:
            written = generate_invoices(SAMPLE_CSV_PATH, Path(tmp), limit=1)
            self.assertEqual(written[0].name, "Invoice-JWNN4UKF-0001.pdf")
            self.assertTrue(written[0].read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
