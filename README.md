# Tony-Yu

Batch-generate Stripe-style invoice PDFs from `data/invoice_data_100.csv`.

## Setup

```bash
pip install -r requirements.txt
```

Inter fonts (`Regular` / `Medium` / `SemiBold`) live in `fonts/` and are embedded into every PDF.

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

## CSV columns

The CSV is UTF-8 and uses these headers:

`序号,发票号码,开票日期,到期日期,货币符号,卖方公司,卖方街道,卖方城市州邮编,卖方国家,卖方邮箱,买方姓名,买方街道,买方城市州邮编,买方国家,买方邮箱,明细名称,明细周期,数量,单价,金额,小计,税费,总计,应付,付款提示`

Dates such as `3-Feb-26` are rendered as `February 3, 2026`. Amounts use thousands separators and two decimal places. An empty `税费` column omits the Tax row.

Currency symbols:

- `$` USD
- `€` EUR
- `¥` / `￥` CNY/JPY
- `₱` PHP (a lone `?` in older GBK exports is treated as peso)
