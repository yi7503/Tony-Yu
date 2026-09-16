#!/usr/bin/env python3
"""Batch-generate Stripe-style invoice PDFs from a CSV file."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


PAGE_W, PAGE_H = letter  # 612 x 792
LEFT = 30.0
RIGHT = 582.0
BILL_TO_X = 250.8
DATE_VALUE_X = 103.5
QTY_RIGHT = 432.75
UNIT_RIGHT = 506.25
AMOUNT_RIGHT = 582.0
TOTAL_LABEL_X = 306.0
LOGO_X = 541.5
LOGO_TOP = 30.0
LOGO_SIZE = 40.5

STRIPE_PURPLE = Color(0x63 / 255, 0x5B / 255, 0xFF / 255)
RULE_GRAY = Color(0.9216, 0.9216, 0.9216)

MONTHS = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

CURRENCY_ALIASES = {
    "?": "₱",
    "￥": "¥",
    "¥": "¥",
    "€": "€",
    "$": "$",
    "₱": "₱",
    "PHP": "₱",
    "EUR": "€",
    "USD": "$",
    "CNY": "¥",
    "JPY": "¥",
    "USD / CNY": "¥",
    "USD/CNY": "¥",
}


@dataclass
class Invoice:
    number: str
    issue_date: str
    due_date: str
    currency: str
    seller_name: str
    seller_street: str
    seller_city: str
    seller_country: str
    seller_email: str
    buyer_name: str
    buyer_street: str
    buyer_city: str
    buyer_country: str
    buyer_email: str
    item_name: str
    item_period: str
    quantity: str
    unit_price: Decimal
    amount: Decimal
    subtotal: Decimal
    tax: Decimal | None
    total: Decimal
    amount_due: Decimal
    pay_label: str


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _find_font(filename: str) -> Path:
    candidates = [
        _script_dir() / "fonts" / filename,
        Path("/usr/share/fonts/truetype/macos") / filename,
        Path("/usr/share/fonts/truetype/inter") / filename,
        Path.home() / ".fonts" / filename,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Missing font {filename}. Place Inter TTF files in { _script_dir() / 'fonts' }."
    )


def find_logo(explicit: Path | None = None) -> Path:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    candidates.extend(
        [
            _script_dir() / "assets" / "logo.png",
            _script_dir() / "logo.png",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Missing logo image. Place logo.png in {_script_dir() / 'assets'}."
    )


def draw_logo(c: canvas.Canvas, logo_path: Path) -> None:
    c.drawImage(
        ImageReader(str(logo_path)),
        LOGO_X,
        PAGE_H - LOGO_TOP - LOGO_SIZE,
        width=LOGO_SIZE,
        height=LOGO_SIZE,
        mask="auto",
        preserveAspectRatio=True,
        anchor="sw",
    )


def register_fonts() -> None:
    mapping = {
        "Inter": "Inter-Regular.ttf",
        "Inter-Medium": "Inter-Medium.ttf",
        "Inter-SemiBold": "Inter-SemiBold.ttf",
    }
    for name, filename in mapping.items():
        pdfmetrics.registerFont(TTFont(name, str(_find_font(filename))))


def text_width(text: str, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, font, size)


def ascent(font: str, size: float) -> float:
    return pdfmetrics.getFont(font).face.ascent / 1000.0 * size


def baseline_from_top(top: float, font: str, size: float) -> float:
    return PAGE_H - top - ascent(font, size)


def parse_decimal(value: str) -> Decimal:
    cleaned = (value or "").strip().replace(",", "")
    if not cleaned:
        raise InvalidOperation(value)
    return Decimal(cleaned)


def parse_optional_decimal(value: str) -> Decimal | None:
    cleaned = (value or "").strip().replace(",", "")
    if not cleaned:
        return None
    return Decimal(cleaned)


def format_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return f"{MONTHS[dt.month]} {dt.day}, {dt.year}"
        except ValueError:
            continue
    return raw


def format_money(symbol: str, value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    return f"{symbol}{quantized:,.2f}"


def normalize_currency(raw: str) -> str:
    token = (raw or "").strip()
    if token in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[token]
    collapsed = " ".join(token.replace("/", " / ").split())
    if collapsed in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[collapsed]
    if token.upper() in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[token.upper()]
    if "CNY" in token.upper() or "人民币" in token:
        return "¥"
    return token or "$"


def cell(row: dict[str, str | None], *keys: str, default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def decode_csv_bytes(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        patched = data.replace(b"\x80", "€".encode("utf-8"))
        try:
            return patched.decode("utf-8")
        except UnicodeDecodeError:
            return data.replace(b"\x80", b"__EURO__").decode("gbk").replace("__EURO__", "€")


def load_invoices(csv_path: Path) -> list[Invoice]:
    text = decode_csv_bytes(csv_path.read_bytes())
    reader = csv.DictReader(text.splitlines())
    invoices: list[Invoice] = []
    for row in reader:
        if not row or not any((value or "").strip() for value in row.values()):
            continue
        number = cell(row, "发票号码")
        if not number:
            continue
        invoices.append(
            Invoice(
                number=number,
                issue_date=format_date(cell(row, "开票日期")),
                due_date=format_date(cell(row, "到期日期")),
                currency=normalize_currency(cell(row, "货币符号", "货币", default="¥")),
                seller_name=cell(row, "卖方公司"),
                seller_street=cell(row, "卖方街道"),
                seller_city=cell(row, "卖方城市州邮编"),
                seller_country=cell(row, "卖方国家"),
                seller_email=cell(row, "卖方邮箱"),
                buyer_name=cell(row, "买方姓名"),
                buyer_street=cell(row, "买方街道"),
                buyer_city=cell(row, "买方城市州邮编"),
                buyer_country=cell(row, "买方国家"),
                buyer_email=cell(row, "买方邮箱"),
                item_name=cell(row, "明细名称"),
                item_period=cell(row, "明细周期", "服务周期"),
                quantity=cell(row, "数量"),
                unit_price=parse_decimal(cell(row, "单价人民币", "单价")),
                amount=parse_decimal(cell(row, "金额人民币", "金额")),
                subtotal=parse_decimal(cell(row, "小计人民币", "小计")),
                tax=parse_optional_decimal(cell(row, "税费")),
                total=parse_decimal(cell(row, "总计人民币", "总计")),
                amount_due=parse_decimal(cell(row, "应付人民币", "应付")),
                pay_label=cell(row, "付款提示", default="Pay online") or "Pay online",
            )
        )
    return invoices


def draw_text(
    c: canvas.Canvas,
    x: float,
    top: float,
    text: str,
    font: str,
    size: float,
    color=black,
    align: str = "left",
) -> None:
    if align == "right":
        x = x - text_width(text, font, size)
    elif align == "center":
        x = x - text_width(text, font, size) / 2.0
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, baseline_from_top(top, font, size), text)


def fill_rect(c: canvas.Canvas, x: float, top: float, width: float, height: float, color) -> None:
    c.setFillColor(color)
    c.rect(x, PAGE_H - top - height, width, height, stroke=0, fill=1)


def draw_invoice(c: canvas.Canvas, invoice: Invoice, logo_path: Path | None = None) -> None:
    symbol = invoice.currency
    due_money = format_money(symbol, invoice.amount_due)
    unit_money = format_money(symbol, invoice.unit_price)
    line_money = format_money(symbol, invoice.amount)
    subtotal_money = format_money(symbol, invoice.subtotal)
    total_money = format_money(symbol, invoice.total)

    fill_rect(c, 0, 0, PAGE_W, PAGE_H, white)
    fill_rect(c, 0, 0, PAGE_W, 4.0, black)

    if logo_path is not None:
        draw_logo(c, logo_path)

    draw_text(c, LEFT, 30.6, "Invoice", "Inter-SemiBold", 18)

    draw_text(c, LEFT, 69.3, "Invoice number", "Inter-SemiBold", 9)
    draw_text(c, DATE_VALUE_X, 69.3, invoice.number, "Inter-SemiBold", 9)
    draw_text(c, LEFT, 82.8, "Date of issue", "Inter-Medium", 9)
    draw_text(c, DATE_VALUE_X, 82.8, invoice.issue_date, "Inter-Medium", 9)
    draw_text(c, LEFT, 96.3, "Date due", "Inter-Medium", 9)
    draw_text(c, DATE_VALUE_X, 96.3, invoice.due_date, "Inter-Medium", 9)

    seller_lines = [
        (invoice.seller_name, "Inter-SemiBold"),
        (invoice.seller_street, "Inter"),
        (invoice.seller_city, "Inter"),
        (invoice.seller_country, "Inter"),
        (invoice.seller_email, "Inter"),
    ]
    buyer_lines = [
        ("Bill to", "Inter-SemiBold"),
        (invoice.buyer_name, "Inter"),
        (invoice.buyer_street, "Inter"),
        (invoice.buyer_city, "Inter"),
        (invoice.buyer_country, "Inter"),
        (invoice.buyer_email, "Inter"),
    ]

    y = 124.8
    for index, (line, font) in enumerate(seller_lines):
        draw_text(c, LEFT, y, line, font, 9)
        y += 16.5 if index == 0 else 13.5

    y = 124.8
    for index, (line, font) in enumerate(buyer_lines):
        draw_text(c, BILL_TO_X, y, line, font, 9)
        y += 16.5 if index == 0 else 13.5
    buyer_bottom = y

    amount_top = max(230.7, buyer_bottom + 21.9)
    draw_text(
        c,
        LEFT,
        amount_top,
        f"{due_money} due {invoice.due_date}",
        "Inter-SemiBold",
        13.5,
    )

    pay_top = amount_top + 26.1
    draw_text(c, LEFT, pay_top, invoice.pay_label, "Inter-SemiBold", 9, color=STRIPE_PURPLE)
    underline_top = pay_top + ascent("Inter-SemiBold", 9) + 0.73
    fill_rect(
        c,
        LEFT,
        underline_top,
        text_width(invoice.pay_label, "Inter-SemiBold", 9),
        0.75,
        STRIPE_PURPLE,
    )

    header_top = pay_top + 41.2
    draw_text(c, LEFT, header_top, "Description", "Inter", 7.5)
    draw_text(c, QTY_RIGHT, header_top, "Qty", "Inter", 7.5, align="right")
    draw_text(c, UNIT_RIGHT, header_top - 0.8, "Unit price", "Inter", 7.5, align="right")
    draw_text(c, AMOUNT_RIGHT, header_top - 0.8, "Amount", "Inter", 7.5, align="right")

    rule_top = header_top + 14.75
    fill_rect(c, LEFT, rule_top, RIGHT - LEFT, 0.75, black)

    item_top = rule_top + 5.55
    draw_text(c, LEFT, item_top, invoice.item_name, "Inter", 9)
    draw_text(c, LEFT, item_top + 13.5, invoice.item_period, "Inter", 9)
    draw_text(c, QTY_RIGHT, item_top, invoice.quantity, "Inter", 9, align="right")
    draw_text(c, UNIT_RIGHT, item_top, unit_money, "Inter", 9, align="right")
    draw_text(c, AMOUNT_RIGHT, item_top, line_money, "Inter", 9, align="right")

    totals: list[tuple[str, str, str]] = [
        ("Subtotal", subtotal_money, "Inter"),
        *((("Tax", format_money(symbol, invoice.tax), "Inter"),) if invoice.tax is not None else ()),
        ("Total", total_money, "Inter"),
        ("Amount due", due_money, "Inter-SemiBold"),
    ]

    row_top = item_top + 13.5 + 29.2
    for label, value, font in totals:
        fill_rect(c, TOTAL_LABEL_X, row_top - 1.75, RIGHT - TOTAL_LABEL_X, 0.75, RULE_GRAY)
        draw_text(c, TOTAL_LABEL_X, row_top, label, font, 9)
        draw_text(c, AMOUNT_RIGHT, row_top, value, font, 9, align="right")
        row_top += 14.25

    fill_rect(c, LEFT, 731.25, RIGHT - LEFT, 0.75, RULE_GRAY)
    draw_text(c, RIGHT, 746.7, "Page 1 of 1", "Inter", 7.5, align="right")

    c.setTitle(f"Invoice {invoice.number}")
    c.setAuthor(invoice.seller_name)
    c.setSubject(f"{due_money} due {invoice.due_date}")


def invoice_filename(invoice: Invoice) -> str:
    safe = invoice.number.replace("/", "-")
    return f"Invoice-{safe}.pdf"


def generate_invoices(
    csv_path: Path,
    output_dir: Path,
    limit: int | None = None,
    logo_path: Path | None = None,
) -> list[Path]:
    register_fonts()
    resolved_logo = find_logo(logo_path)
    invoices = load_invoices(csv_path)
    if limit is not None:
        invoices = invoices[:limit]
    if not invoices:
        raise SystemExit(f"No invoices found in {csv_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for invoice in invoices:
        path = output_dir / invoice_filename(invoice)
        c = canvas.Canvas(str(path), pagesize=letter)
        draw_invoice(c, invoice, resolved_logo)
        c.showPage()
        c.save()
        written.append(path)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Stripe-style invoice PDFs from invoice_data_100.csv"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=_script_dir() / "data" / "invoice_data_100.csv",
        help="Path to the invoice CSV",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_script_dir() / "output",
        help="Directory to write PDF files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate only the first N invoices",
    )
    parser.add_argument(
        "--logo",
        type=Path,
        default=None,
        help="Path to the top-right logo PNG (default: assets/logo.png)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = generate_invoices(args.csv, args.out, args.limit, args.logo)
    print(f"Generated {len(paths)} invoice PDF(s) in {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
