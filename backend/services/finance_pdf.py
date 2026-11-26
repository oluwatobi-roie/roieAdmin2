"""Customer PDFs built solely from stored finance snapshots; no network access."""
import io
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Flowable

from services.finance import invoice_view, receipt_view

# Embed the bundled fonts, including accented customer names, on slim Docker images.
import reportlab
_font_dir = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Roie", str(_font_dir / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("RoieBold", str(_font_dir / "VeraBd.ttf")))
pdfmetrics.registerFontFamily("Roie", normal="Roie", bold="RoieBold", italic="Roie", boldItalic="RoieBold")
BLUE = colors.HexColor("#1e3a8a")
MUTED = colors.HexColor("#64748b")
LIGHT = colors.HexColor("#eff6ff")
WIDTH = A4[0] - 80
STYLES = {
    "body": ParagraphStyle("body", fontName="Roie", fontSize=9, leading=14, textColor=colors.HexColor("#334155"), spaceAfter=5),
    "small": ParagraphStyle("small", fontName="Roie", fontSize=8, leading=12, textColor=MUTED, spaceAfter=4),
    "heading": ParagraphStyle("heading", fontName="RoieBold", fontSize=12, leading=17, textColor=BLUE, spaceBefore=14, spaceAfter=8, keepWithNext=True),
    "brand": ParagraphStyle("brand", fontName="RoieBold", fontSize=23, leading=30, textColor=BLUE, spaceAfter=6),
    "right": ParagraphStyle("right", fontName="Roie", fontSize=8, leading=12, alignment=TA_RIGHT),
}
ITEMS = {
    "Device": ("GPS_D_V4", "Intelligent GPS Tracker Device for Automobile", 0),
    "GPRS fee": ("GPRS_GSM", "GSM Access Fee for 12 months per module (MTN)", 1),
    "Server fee": ("GPS_Server_Maintenance", "Global Server App License Fee for 1 year per module", 2),
    "Installation": ("Installation", "Logistics, Installation", 3),
}
TITLES = {"installation": "Installations", "renewal": "Renewal", "maintenance": "Maintenance", "special": "Special Service"}
SALES_TERMS = json.loads(Path(__file__).with_name("invoice_terms.json").read_text(encoding="utf-8"))


def money(minor):
    return f"NGN {minor // 100:,}.{minor % 100:02d}"


def paragraph(value, style="body"):
    # Customer input must never be interpreted as ReportLab markup or links.
    return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), STYLES[style])


class Stamp(Flowable):
    width, height = 170, 60

    def __init__(self, status):
        Flowable.__init__(self)
        self.width, self.height = 170, 60
        self.status = status

    def draw(self):
        label, color = {"paid": ("PAID IN FULL", "#15803d"), "partial": ("PARTIALLY PAID", "#a16207"),
                        "unpaid": ("UNPAID", "#b91c1c")}[self.status]
        canvas = self.canv
        canvas.saveState()
        canvas.translate(85, 26)
        canvas.rotate(9)
        canvas.setStrokeColor(colors.HexColor(color))
        canvas.setFillColor(colors.HexColor(color))
        canvas.setLineWidth(1.5)
        canvas.roundRect(-76, -16, 152, 32, 4, fill=0)
        canvas.setFont("RoieBold", 11)
        canvas.drawCentredString(0, -4, label)
        canvas.restoreState()


def table(rows, widths):
    result = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1, splitInRow=1)
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return result


def groups(entries):
    result = {}
    for index, entry in enumerate(entries):
        key = json.dumps([entry["category"], entry.get("activity", ""), entry.get("task_notes", ""),
                          entry["total_minor"], entry["breakdown"], index if entry["category"] == "special" else None], sort_keys=True)
        result.setdefault(key, []).append(entry)
    return list(result.values())


def document_pdf(invoice, kind="invoice", payment_id=None):
    doc = invoice_view(invoice) if kind == "invoice" else receipt_view(invoice, payment_id)
    title = "Customer invoice" if kind == "invoice" else "Payment receipt" if payment_id else "Combined payment receipt"
    story = [paragraph("RoieTrackers", "brand"), paragraph(title + " | " + doc["number"], "heading")]
    if kind == "invoice":
        story.append(paragraph("Issued: " + doc["issued_at"][:10] + ("   Due: " + doc["due_date"] if doc.get("due_date") else ""), "small"))
    else:
        story.append(paragraph("Invoice: " + doc["invoice_number"] + "   Date: " + doc["as_of"][:10], "small"))
    contact = doc["customer"]
    contact_lines = [paragraph("Bill to", "small")] + [paragraph(contact.get(key, "")) for key in ("name", "email", "phone", "formatted_address") if contact.get(key)]
    status = doc["payment_status"] if kind == "invoice" else "paid" if doc["balance_minor"] == 0 else "partial"
    right_column = [Stamp(status)]
    if kind == "invoice":
        right_column.extend([Spacer(1, 8), paragraph("Payment details", "body"),
            paragraph("Bank Name: GTBank\nAccount Number: 0421439134\nAccount Name: Roie Technologies Ltd", "small")])
    billing = Table([[contact_lines, right_column]], colWidths=[WIDTH - 180, 180])
    billing.setStyle(TableStyle([("VALIGN", (0,0),(-1,-1),"TOP"), ("LEFTPADDING", (0,0),(-1,-1),0), ("RIGHTPADDING", (0,0),(-1,-1),0)]))
    story.extend([Spacer(1, 10), billing, Spacer(1, 10)])
    if kind == "invoice":
        for category, title in TITLES.items():
            selected = [group for group in groups(doc["entries"]) if group[0]["category"] == category]
            if not selected:
                continue
            story.append(paragraph(title, "heading"))
            for group in selected:
                entry, quantity = group[0], len(group)
                for key in ("activity", "task_notes"):
                    if entry.get(key):
                        story.append(paragraph(entry[key]))
                rows = [[paragraph(label, "small" if index == 0 else "right") for index, label in enumerate(("Item", "Qty", "Price", "Amount"))]]
                parts = []
                for part in entry["breakdown"]:
                    label, description, order = ITEMS.get(part["label"], (part["label"], part.get("description", ""), 4)) if category != "special" else (part["label"], part.get("description", ""), 4)
                    parts.append((order, label, description, part["amount_minor"]))
                for _, label, description, amount in sorted(parts, key=lambda part: part[0]):
                    rows.append([[paragraph(label), paragraph(description, "small")], paragraph(quantity, "right"), paragraph(money(amount), "right"), paragraph(money(amount * quantity), "right")])
                story.append(table(rows, [WIDTH-238, 36, 98, 104]))
                if category != "special":
                    names = [(item.get("device") or {}).get("name") or item.get("vehicle_label") or item.get("activity") or "Vehicle" for item in group]
                    names = [name + (" (awaiting installation)" if not item.get("device") else "") for name, item in zip(names, group)]
                    story.extend([Spacer(1, 6), paragraph(f"Vehicles for {title.lower()} ({quantity}): " + ", ".join(names))])
            story.append(paragraph(title + " subtotal: " + money(sum(item["total_minor"] for group in selected for item in group)), "right"))
        totals = [("Subtotal", doc.get("subtotal_minor", doc["total_minor"]))]
        if doc.get("discount_minor"):
            discount = doc.get("discount", {})
            label = "Discount" + (f" ({discount['value']}%)" if discount.get("type") == "percent" else "")
            totals.append((label, -doc["discount_minor"]))
        totals.extend([("Total", doc["total_minor"]), ("Paid", doc["paid_minor"]), ("Balance", doc["balance_minor"])])
    else:
        rows = [[paragraph("Date / reference", "small"), paragraph("Method", "small"), paragraph("Received", "right")]]
        for payment in doc["payments"]:
            rows.append([paragraph(payment["paid_on"] + "\n" + (payment.get("reference") or "")), paragraph(payment["method"].replace("_", " ")), paragraph(money(payment["amount_minor"]), "right")])
        story.append(table(rows, [WIDTH-244, 130, 114]))
        totals = [("Received", doc["received_minor"]), ("Invoice total", doc["invoice_total_minor"]), ("Total paid as of this receipt", doc["cumulative_paid_minor"]), ("Remaining balance", doc["balance_minor"])]
    story.append(KeepTogether([Spacer(1, 14)] + [paragraph(label + ": " + ("-" if amount < 0 else "") + money(abs(amount)), "right") for label, amount in totals]))
    if kind == "invoice":
        if doc.get("notes"):
            story.extend([paragraph("Notes", "heading"), paragraph(doc["notes"])])
        if any(entry["category"] == "installation" for entry in doc["entries"]):
            terms = [paragraph("Sales Terms", "heading")]
            terms.extend(paragraph(f"{index}. {term}", "small") for index, term in enumerate(SALES_TERMS, 1))
            terms.extend([Spacer(1, 16), paragraph("Customer signature: ________________________    Date: ______________", "small")])
            story.append(KeepTogether(terms))
    else:
        story.extend([Spacer(1, 20), paragraph("Thank you for choosing RoieTrackers.", "small")])
    output = io.BytesIO()
    def footer(canvas, pdf):
        canvas.saveState()
        canvas.setFont("Roie", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(40, 25, doc["number"])
        canvas.drawRightString(A4[0]-40, 25, f"Page {pdf.page}")
        canvas.restoreState()
    SimpleDocTemplate(output, invariant=True, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=32, bottomMargin=45,
                      title=title + " " + doc["number"], author="RoieTrackers").build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue(), doc["number"]
