import os
import re
from datetime import datetime

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


# ──────────────────────────────────────────────
# 1. FOLDER SETUP
# ──────────────────────────────────────────────

def create_timetables_folder():
    """Create 'My Generated Timetables' folder inside the same folder as this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(script_dir, "My Generated Timetables")
    os.makedirs(folder, exist_ok=True)
    return folder


# ──────────────────────────────────────────────
# 2. EXAM PERIOD DETECTION
# ──────────────────────────────────────────────

def detect_exam_period(filename, text):
    """Return 'June' or 'November' from filename or PDF content."""
    combined = (filename + " " + text[:500]).lower()
    if "month 6" in combined or "june" in combined or "jun" in combined:
        return "June"
    if "month 11" in combined or "november" in combined or "nov" in combined:
        return "November"
    return None


# ──────────────────────────────────────────────
# 3. PDF TEXT EXTRACTION
# ──────────────────────────────────────────────

def extract_text_from_pdf(pdf_path):
    """Extract all text from every page of a PDF."""
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            print(f"   -> {total} page(s) found.")
            for i, page in enumerate(pdf.pages, 1):
                print(f"   Processing page {i}/{total}...", end="\r")
                text = page.extract_text()
                if text:
                    pages.append(text)
        print()
        return "\n".join(pages)
    except Exception as exc:
        print(f"\n❌  Error reading PDF: {exc}")
        return None


# ──────────────────────────────────────────────
# 4. TIMETABLE PARSING
# ──────────────────────────────────────────────

LINE_RE = re.compile(
    r"""
    ^\s*\d+\s+
    ([A-Z]{2,5}\d{3,4}[A-Z0-9]*)
    \s+\S+\s+
    .+?
    (\d{2}-[A-Z]{3}-\d{4})
    \s+(\d{2}:\d{2})
    """,
    re.VERBOSE,
)

MONTH_MAP = {
    "JAN": "January", "FEB": "February", "MAR": "March",
    "APR": "April",   "MAY": "May",      "JUN": "June",
    "JUL": "July",    "AUG": "August",   "SEP": "September",
    "OCT": "October", "NOV": "November", "DEC": "December",
}

def format_date(raw):
    """Convert '02-JUN-2026' to 'Tuesday, 02 June 2026'."""
    try:
        day, mon, year = raw.split("-")
        month_name = MONTH_MAP.get(mon.upper(), mon)
        dt = datetime.strptime(f"{day} {month_name} {year}", "%d %B %Y")
        return dt.strftime("%A, %d %B %Y")
    except Exception:
        return raw

def format_time(raw):
    """Convert '08:30' to '8:30 AM', '14:00' to '2:00 PM'."""
    try:
        dt = datetime.strptime(raw, "%H:%M")
        return dt.strftime("%-I:%M %p")
    except Exception:
        return raw

def sort_key(exam):
    """Sort exams by date then time."""
    try:
        return datetime.strptime(
            exam["_raw_date"] + " " + exam["_raw_time"], "%d-%b-%Y %H:%M"
        )
    except Exception:
        return datetime.max

def parse_timetable(text):
    """Return list of dicts with Subject, Date, Time (plus raw fields for sorting)."""
    exams = []
    seen = set()

    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        code     = m.group(1).upper()
        raw_date = m.group(2)
        raw_time = m.group(3)

        key = (code, raw_date, raw_time)
        if key in seen:
            continue
        seen.add(key)

        exams.append({
            "Subject":   code,
            "Date":      format_date(raw_date),
            "Time":      format_time(raw_time),
            "_raw_date": raw_date,
            "_raw_time": raw_time,
        })

    exams.sort(key=sort_key)
    return exams


# ──────────────────────────────────────────────
# 5. MODULE LOOKUP
# ──────────────────────────────────────────────

def find_modules(all_exams, codes):
    """Filter the full exam list to only the requested module codes, sorted by date/time."""
    codes = [c.strip().upper() for c in codes]
    found, missing = [], []

    for code in codes:
        matches = [e for e in all_exams if e["Subject"] == code]
        if matches:
            found.extend(matches)
        else:
            missing.append(code)

    found.sort(key=sort_key)
    return found, missing


# ──────────────────────────────────────────────
# 6. FILENAME RESOLVER
# ──────────────────────────────────────────────

def resolve_filename(save_folder):
    """Ask the user what to name the PDF and ensure no clash with existing files."""
    existing = {
        f.lower()
        for f in os.listdir(save_folder)
        if f.lower().endswith(".pdf")
    }

    while True:
        print("\nWhat would you like to name this PDF?")
        raw = input("(e.g. My June Timetable): ").strip()

        if not raw:
            print("❌  Name cannot be empty. Please try again.")
            continue

        # Strip characters that are illegal in filenames on Windows / Mac / Linux
        safe = re.sub(r'[\\/*?:"<>|]', "", raw).strip()
        if not safe:
            print("❌  That name contains only invalid characters. Please try again.")
            continue

        filename = safe if safe.lower().endswith(".pdf") else safe + ".pdf"

        if filename.lower() in existing:
            print(f"⚠️   A file called '{filename}' already exists in that folder.")
            print("    Please choose a different name.")
            continue

        return filename


# ──────────────────────────────────────────────
# 7. PDF GENERATION
# ──────────────────────────────────────────────

def build_pdf(exams, period, save_folder, filename):
    """Create a nicely formatted personal exam timetable PDF."""
    full_path = os.path.join(save_folder, filename)

    doc = SimpleDocTemplate(
        full_path,
        pagesize=A4,
        rightMargin=50, leftMargin=50,
        topMargin=60,   bottomMargin=60,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title2",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor("#1a237e"),
        spaceAfter=6,
        alignment=1,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=4,
        alignment=1,
    )
    warn_style = ParagraphStyle(
        "Warn",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#b71c1c"),
        alignment=1,
        spaceBefore=16,
    )

    elements = []

    elements.append(Paragraph(f"My {period} Examination Timetable", title_style))
    elements.append(Paragraph("University of Limpopo · 2026", sub_style))
    elements.append(Paragraph(
        f"Generated on {datetime.now().strftime('%d %B %Y at %I:%M %p')}  ·  {len(exams)} exam(s)",
        sub_style,
    ))
    elements.append(Spacer(1, 18))

    header = ["Module Code", "Date", "Time"]
    rows   = [header] + [[e["Subject"], e["Date"], e["Time"]] for e in exams]

    col_widths = [1.6 * inch, 3.2 * inch, 1.4 * inch]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)

    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 11),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 10),
        ("ALIGN",         (0, 1), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#e8eaf6"), colors.white]),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#9fa8da")),
        ("LINEBELOW",     (0, 0), (-1, 0),  1.5, colors.HexColor("#283593")),
    ]))

    elements.append(tbl)

    elements.append(Paragraph(
        "⚠  Always verify exam details against the official university timetable.",
        warn_style,
    ))

    doc.build(elements)
    return full_path


# ──────────────────────────────────────────────
# 8. MAIN LOOP
# ──────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  🎓  EXAM TIMETABLE GENERATOR  -  University of Limpopo")
    print("=" * 60)

    save_folder = create_timetables_folder()
    print(f"\n📁  Timetables will be saved to:\n    {save_folder}\n")

    while True:
        print("-" * 60)
        print("STEP 1 – Provide the general exam timetable PDF")
        print("  Tip: In VS Code's terminal you can right-click the file")
        print("       and choose 'Copy Path', then paste it here.")
        raw_path = input("\nPDF file path: ").strip().strip('"').strip("'")

        if not os.path.isfile(raw_path):
            print("❌  File not found. Please check the path and try again.\n")
            continue

        if not raw_path.lower().endswith(".pdf"):
            print("❌  Only PDF files are supported.\n")
            continue

        print("\n📖  Reading PDF ...")
        text = extract_text_from_pdf(raw_path)

        if not text:
            print("❌  Could not extract text. The PDF may be a scanned image.\n")
            continue

        period = detect_exam_period(os.path.basename(raw_path), text)
        if not period:
            print("\n❓  Could not auto-detect June / November from the file.")
            while True:
                period = input("   Enter 'June' or 'November': ").strip().capitalize()
                if period in ("June", "November"):
                    break
                print("   Please type exactly 'June' or 'November'.")

        print(f"✅  Detected exam period: {period}")
        print("🔍  Parsing timetable ...")
        all_exams = parse_timetable(text)
        print(f"   Found {len(all_exams)} unique exam entries in the PDF.")

        if not all_exams:
            print("❌  No exam entries could be parsed. The PDF format may differ.\n")
            continue

        print("\n" + "-" * 60)
        print("STEP 2 – Enter YOUR module codes")
        print("  Separate multiple codes with commas.")
        print("  Example:  SMTH011, SSTA011, SCLA011")
        raw_codes = input("\nModule codes: ").strip()

        codes = [c.strip() for c in raw_codes.split(",") if c.strip()]
        if not codes:
            print("❌  No module codes entered.\n")
            continue

        found, missing = find_modules(all_exams, codes)

        if missing:
            print(f"\n⚠️   Module(s) NOT found in the timetable: {', '.join(missing)}")
            print("    Double-check spelling/capitalisation against the PDF.")

        if not found:
            print("❌  None of your modules were found. Cannot generate timetable.\n")
            continue

        print(f"\n✅  Found {len(found)} exam(s):")
        for e in found:
            print(f"   • {e['Subject']:12s}  {e['Date']}  at  {e['Time']}")

        print("\n" + "-" * 60)
        print("STEP 3 – Name your PDF")
        filename = resolve_filename(save_folder)

        print("\n📄  Generating PDF ...")
        pdf_path = build_pdf(found, period, save_folder, filename)
        print(f"\n🎉  Done!  Saved to:\n    {pdf_path}")

        print("\n" + "=" * 60)
        again = input("\nGenerate another timetable? (yes / no): ").strip().lower()
        if again not in ("yes", "y"):
            print("\n👋  All done! Your timetable(s) are in the folder:")
            print(f"    {save_folder}\n")
            break


if __name__ == "__main__":
    main()
