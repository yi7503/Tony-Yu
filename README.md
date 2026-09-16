# Tony-Yu

Batch-generate Stripe-style invoice PDFs from `data/invoice_data_100.csv`.

## Setup

```bash
pip install -r requirements.txt
```

Inter fonts (`Regular` / `Medium` / `SemiBold`) live in `fonts/` and are embedded into every PDF. The top-right mark is `assets/logo.png` (override with `--logo`).

## Generate invoices

```bash
python generate_invoices.py
```

This reads `data/invoice_data_100.csv` and writes 100 files to `output/` (gitignored), named like `Invoice-UJ6LCDHK-0001.pdf`.

Two preview PDFs are in `examples/`: one without tax and one with a Tax row.

```bash
python -m unittest test_generate_invoices.py
```

Useful options:

```bash
python generate_invoices.py --csv path/to/invoices.csv --out output --limit 5
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--csv` | `data/invoice_data_100.csv` | Source CSV |
| `--out` | `output` | Output directory |
| `--limit N` | all rows | Only the first N invoices |
| `--logo` | `assets/logo.png` | Top-right logo image |

## CSV columns

The CSV is UTF-8. Two layouts are supported:

1. Original: `货币符号`, `明细周期`, `单价`, `金额`, `小计`, `总计`, `应付`
2. Dual-currency sample (`data/invoice_sample_data.csv`): `货币`, `服务周期`, `单价USD`, `金额USD`. Invoices render in `$` (USD columns only).

Dates such as `3-Feb-26` are rendered as `February 3, 2026`. Amounts use thousands separators and two decimal places. An empty `税费` column omits the Tax row.

Currency symbols:

- `$` USD
- `€` EUR
- `¥` / `￥` CNY/JPY
- `₱` PHP (a lone `?` in older GBK exports is treated as peso)
