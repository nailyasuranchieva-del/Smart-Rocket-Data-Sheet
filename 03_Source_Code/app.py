import os 
import uuid
import sqlite3
import shutil
from io import BytesIO
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# Load private Telegram settings from .env.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(Path(__file__).resolve().parent / ".env")

DB_PATH = BASE_DIR / "04_Database" / "srds.db"
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    """Create the table and safely add newer fields without deleting records."""
    db_already_existed = DB_PATH.exists()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant TEXT NOT NULL,
                project TEXT NOT NULL,
                team TEXT,
                email TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        existing = {
            row[1] for row in conn.execute("PRAGMA table_info(registrations)")
        }
        new_columns = {
            "rocket_name": "TEXT",
            "owner_name": "TEXT",
            "address": "TEXT",
            "city": "TEXT",
            "state": "TEXT",
            "zip_code": "TEXT",
        }
        missing = [column for column in new_columns if column not in existing]

        backup_path = DB_PATH.parent / "srds_before_v07_backup.db"
        if db_already_existed and missing and not backup_path.exists():
            shutil.copy2(DB_PATH, backup_path)

        for column in missing:
            conn.execute(
                f"ALTER TABLE registrations ADD COLUMN {column} {new_columns[column]}"
            )


def get_fonts():
    regular_path = Path("C:/Windows/Fonts/arial.ttf")
    bold_path = Path("C:/Windows/Fonts/arialbd.ttf")
    regular, bold = "Helvetica", "Helvetica-Bold"

    if regular_path.exists():
        if "SRDS" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("SRDS", str(regular_path)))
        regular = "SRDS"

    if bold_path.exists():
        if "SRDS-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("SRDS-Bold", str(bold_path)))
        bold = "SRDS-Bold"

    return regular, bold


def header(pdf, page, font, bold):
    width, height = A4
    pdf.setFillColorRGB(0.08, 0.12, 0.18)
    pdf.setFont(bold, 15)
    pdf.drawString(35, height - 38, "SMART ROCKET DATA SHEET")
    pdf.setFillColorRGB(0.25, 0.29, 0.34)
    pdf.setFont(font, 8)
    pdf.drawRightString(width - 35, height - 38, f"SRDS | PAGE {page} OF 2")
    pdf.setStrokeColorRGB(0.15, 0.18, 0.22)
    pdf.setLineWidth(0.8)
    pdf.line(35, height - 49, width - 35, height - 49)
    pdf.setFillColorRGB(0, 0, 0)


def section(pdf, x, y, width, title, bold, height=18):
    pdf.setFillColorRGB(0.15, 0.18, 0.22)
    pdf.roundRect(x, y - height, width, height, 2, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont(bold, 8)
    pdf.drawString(x + 7, y - 12.2, title.upper())
    pdf.setFillColorRGB(0, 0, 0)
    return y - height - 9


def field(pdf, x, y, width, label, font, size=7.1, step=22):
    pdf.setFont(font, size)
    pdf.drawString(x, y, str(label)[:115])
    pdf.setStrokeColorRGB(0.35, 0.38, 0.42)
    pdf.setLineWidth(0.4)
    pdf.line(x, y - 9, x + width, y - 9)
    return y - step


def checklist(pdf, x, y, width, options, font, columns=1, size=6.6, row_height=14):
    columns = max(1, columns)
    col_width = width / columns
    rows = (len(options) + columns - 1) // columns

    for i, option in enumerate(options):
        col = i // rows if rows else 0
        row = i % rows if rows else 0
        xx = x + col * col_width
        yy = y - row * row_height
        pdf.setLineWidth(0.55)
        pdf.rect(xx, yy - 2, 7, 7, fill=0, stroke=1)
        pdf.setFont(font, size)
        pdf.drawString(xx + 12, yy - 0.2, option)

    return y - rows * row_height - 5


def heading(pdf, x, y, text, bold):
    pdf.setFont(bold, 7.2)
    pdf.drawString(x, y, text.upper())
    return y - 14


def fields(pdf, x, y, width, labels, font, size=6.8, step=19):
    for label in labels:
        y = field(pdf, x, y, width, label, font, size=size, step=step)
    return y


def create_pdf(record):
    # id, participant, project, team, email, created_at,
    # rocket_name, owner_name, address, city, state, zip_code
    (record_id, participant, project, team, email, created_at,
     rocket_name, owner_name, address, city, state, zip_code) = record

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    font, bold = get_fonts()
    left, right = 35, page_width - 35
    total_width = right - left
    gap = 12

    # PAGE 1: identity and model description, using the page more evenly.
    header(pdf, 1, font, bold)
    y = page_height - 66

    y = section(pdf, left, y, total_width, "Rocket and owner information", bold)
    half = (total_width - 18) / 2
    x_right = left + half + 18

    y_left = fields(pdf, left + 6, y, half - 12, [
        f"Rocket name: {rocket_name or project}",
        f"Owner's name: {owner_name or participant}",
        f"Address: {address or ''}",
    ], font, size=7.0, step=22)
    y_right = fields(pdf, x_right, y, half - 12, [
        f"Team: {team or ''}",
        f"City: {city or ''}",
        f"State / Region: {state or ''}     Zip: {zip_code or ''}",
    ], font, size=7.0, step=22)
    y = min(y_left, y_right) - 3

    y = section(pdf, left, y, total_width, "Registration information", bold)
    third = (total_width - 24) / 3
    fields(pdf, left + 6, y, third - 12, [f"Participant: {participant}"],
           font, size=6.8, step=19)
    fields(pdf, left + third + 6, y, third - 12, [f"Email: {email or ''}"],
           font, size=6.8, step=19)
    fields(pdf, left + 2 * third + 6, y, third - 12,
           [f"Registration: SRDS-{record_id:04d}", f"Date: {created_at}"],
           font, size=6.5, step=19)
    y -= 43

    y = section(pdf, left, y, total_width, "Model description", bold)
    col_width = (total_width - 3 * gap) / 4
    xs = [left + i * (col_width + gap) for i in range(4)]

    yy = heading(pdf, xs[0], y, "Type of rocket", bold)
    checklist(pdf, xs[0], yy, col_width, [
        "Sport", "Multi-stage", "Cluster of motors", "Competition",
        "Scale model", "Fantasy type", "Payload carrier",
        "High-power rocket", "Radio controlled"
    ], font, columns=1, size=6.2, row_height=14)

    fields(pdf, xs[1], y, col_width, [
        "Length", "Diameter", "Number of fins", "Empty mass",
        "Estimated drag coefficient", "Color", "Nose shape"
    ], font, size=6.4, step=22)

    fields(pdf, xs[2], y, col_width, [
        "CP location", "CG location", "Date of design",
        "Date of construction", "Number of stages",
        "Number of motors", "Fin shape"
    ], font, size=6.4, step=22)

    yy = field(pdf, xs[3], y, col_width, "Fin area (single fin)",
               font, size=6.4, step=21)
    yy = heading(pdf, xs[3], yy, "Fin airfoil shape", bold)
    yy = checklist(pdf, xs[3], yy, col_width, [
        "Square edges", "Rounded edges", "Chambered airfoil", "Symmetrical airfoil"
    ], font, columns=1, size=5.9, row_height=13)
    yy = field(pdf, xs[3], yy, col_width, "Recommended motors",
               font, size=6.1, step=20)
    yy = checklist(pdf, xs[3], yy, col_width, ["Scratch-built", "Kit"],
                   font, columns=1, size=6.1, row_height=13)
    field(pdf, xs[3], yy, col_width, "Kit manufacturer",
          font, size=6.1, step=20)

    pdf.setFont(font, 6.5)
    pdf.drawString(left, 24, "SRDS | Tournament documentation")
    pdf.showPage()

    # PAGE 2: descriptive form sections; technical fields stay blank.
    header(pdf, 2, font, bold)
    y_top = page_height - 66
    box_width = (total_width - 15) / 2
    lx, rx = left, left + box_width + 15

    yl = section(pdf, lx, y_top, box_width, "Primary recovery system", bold)
    yr = section(pdf, rx, y_top, box_width, "Secondary recovery system", bold)
    recovery = [
        "Tumble recovery", "Streamer", "Parachute", "Glider",
        "Helicopter", "Drag brakes", "Horizontal spin"
    ]
    yl = checklist(pdf, lx + 6, yl, box_width - 12, recovery,
                   font, size=6.5, row_height=14)
    yr = checklist(pdf, rx + 6, yr, box_width - 12, recovery,
                   font, size=6.5, row_height=14)
    y_mid = min(yl, yr) - 3

    yl = section(pdf, lx, y_mid, box_width, "Parachute description", bold)
    yr = section(pdf, rx, y_mid, box_width, "Streamer description", bold)

    yl = heading(pdf, lx + 6, yl, "Parachute shape", bold)
    yl = checklist(pdf, lx + 6, yl, box_width - 12,
                   ["Circle", "Square", "Hexagon", "Octagon"],
                   font, columns=2, size=6.4, row_height=14)
    yl = heading(pdf, lx + 6, yl, "Material", bold)
    yl = checklist(pdf, lx + 6, yl, box_width - 12,
                   ["Plastic", "Cloth"],
                   font, columns=2, size=6.4, row_height=14)

    yl = fields(pdf, lx + 6, yl, box_width - 12, [
        "Canopy area", "Color", "Mass", "Number of shroud lines",
        "Shroud line length"
    ], font, size=6.4, step=19)

    yr = heading(pdf, rx + 6, yr, "Material", bold)
    yr = checklist(pdf, rx + 6, yr, box_width - 12,
                   ["Paper", "Plastic", "Cloth"],
                   font, columns=2, size=6.4, row_height=14)
    yr = fields(pdf, rx + 6, yr, box_width - 12,
                ["Length", "Width", "Color", "Mass"],
                font, size=6.4, step=19)

   
    y_bottom = min(yl, yr) - 3

    yl = section(pdf, lx, y_bottom, box_width, "Helicopter description", bold)
    yr = section(pdf, rx, y_bottom, box_width, "Glider description", bold)

    yl = fields(pdf, lx + 6, yl, box_width - 12, [
        "Number of blades", "Blade area (one blade)", "Blade length",
        "Blade chord length", "Blade mount angle", "Rotor disk area"
    ], font, size=6.2, step=18)
    yl = heading(pdf, lx + 6, yl, "Blade position", bold)
    yl = checklist(pdf, lx + 6, yl, box_width - 12,
                   ["Carried internally", "Hinged near front",
                    "Hinged near rear"], font, size=6.1, row_height=13)
    yl = heading(pdf, lx + 6, yl, "Blade type", bold)
    checklist(pdf, lx + 6, yl, box_width - 12,
              ["Flat", "Chambered", "Symmetrical"],
              font, size=6.1, row_height=13)

    yr = heading(pdf, rx + 6, yr, "Vehicle", bold)
    yr = checklist(pdf, rx + 6, yr, box_width - 12,
                   ["Primary vehicle", "Parasite on rocket"],
                   font, columns=2, size=5.9, row_height=13)

    yr = heading(pdf, rx + 6, yr, "Glider type", bold)
    yr = checklist(pdf, rx + 6, yr, box_width - 12,
                   ["Boost-glider", "Rocket-glider"],
                   font, columns=2, size=5.9, row_height=13)

    yr = heading(pdf, rx + 6, yr, "Glider configuration", bold)
    yr = checklist(pdf, rx + 6, yr, box_width - 12,
                   ["Conventional", "Canard", "Flying wing"],
                   font, columns=2, size=5.9, row_height=13)
    fields(pdf, rx + 6, yr, box_width - 12, [
        "Length", "Wing span", "Wing area", "Chord length", "CG (glide)",
        "Wing sweep angle", "Glide mass", "Dihedral angle",
        "Horizontal tail area", "Vertical tail area",
        "Horizontal tail span", "Vertical tail span",
        "Horizontal tail chord", "Vertical tail chord"
    ], font, size=5.8, step=16)

    pdf.setFont(font, 6)
    pdf.drawString(left, 15,
                   "SRDS | Technical fields are intentionally left blank for manual completion")
    pdf.save()
    buffer.seek(0)
    return buffer


def send_pdf_to_telegram(record_id, participant, pdf_buffer):
    """Send one notification with the generated PDF attached to the private chat."""
    if not BOT_TOKEN or not CHAT_ID:
        return False, "Telegram settings are missing. Check the private .env file."

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    caption = (
        f"Новая регистрация SRDS-{record_id:04d}\n"
        f"Участник: {participant}"
    )
    try:
        pdf_buffer.seek(0)
        response = requests.post(
            url,
            data={"chat_id": CHAT_ID, "caption": caption},
            files={
                "document": (
                    f"SRDS_{record_id:04d}.pdf",
                    pdf_buffer.getvalue(),
                    "application/pdf",
                )
            },
            timeout=30,
        )
        result = response.json()
        if result.get("ok"):
            return True, "PDF sent"
        return False, result.get("description", "Telegram rejected the request")
    except requests.RequestException:
        return False, "Could not connect to Telegram. The registration is still saved."


init_db()

st.set_page_config(
    page_title="Smart Rocket Data Sheet",
    page_icon="📋",
    layout="centered",
)


st.title("Smart Rocket Data Sheet")
st.subheader("Система регистрации участников турнира")
st.caption("Registration form")
st.divider()

st.header("Регистрация участника")
st.write("Заполните форму и нажмите «Отправить регистрацию».")

with st.form("registration_form", clear_on_submit=True):
    st.subheader("Данные участника")
    participant = st.text_input("Имя и фамилия участника *")
    email = st.text_input("Электронная почта")

    st.subheader("Данные владельца и проекта")
    rocket_name = st.text_input("Rocket name / Название ракеты *")
    owner_name = st.text_input("Owner's name / Имя владельца *")
    team = st.text_input("Team / Команда")
    address = st.text_input("Address / Адрес")
    city = st.text_input("City / Город")
    state = st.text_input("State / Область или регион")
    zip_code = st.text_input("Zip / Почтовый индекс")

    submitted = st.form_submit_button("Отправить регистрацию", type="primary")


if submitted:
    if participant.strip() and rocket_name.strip() and owner_name.strip():
        try:
            registration_id = str(uuid.uuid4())

            response = supabase.table("registrations").insert({
                "participant": participant.strip(),
                "participant_name": participant.strip(),
                "registration_id": registration_id,
                "project": rocket_name.strip(),
                "team": team.strip(),
                "email": email.strip(),
                "rocket_name": rocket_name.strip(),
                "owner_name": owner_name.strip(),
                "address": address.strip(),
                "city": city.strip(),
                "state": state.strip(),
                "zip_code": zip_code.strip(),
            }).select("*").execute()

            row = response.data[0]
            record_id = int(row["id"])

            record = (
                record_id,
                row["participant"],
                row["project"],
                row.get("team"),
                row.get("email"),
                row.get("created_at"),
                row.get("rocket_name"),
                row.get("owner_name"),
                row.get("address"),
                row.get("city"),
                row.get("state"),
                row.get("zip_code"),
            )

            pdf_buffer = create_pdf(record)
            sent, message = send_pdf_to_telegram(
                record_id, participant.strip(), pdf_buffer
            )

            if sent:
                st.success("Регистрация успешно отправлена!")
            else:
                st.warning(f"Регистрация сохранена, но Telegram: {message}")

        except Exception as e:
            st.error(f"Ошибка сохранения регистрации: {e}")


       
    else:
        st.warning(
            "Заполните обязательные поля: участник, название ракеты и владелец."
        )

st.caption("После отправки заявки вы увидите подтверждение. PDF направляется организаторам.")


