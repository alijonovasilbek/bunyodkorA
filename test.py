import json
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor


# =========================
# DB CONFIG (O'ZGARTIRING)
# =========================
DB_CONFIG = {
    "host": "localhost",       # masalan: localhost yoki server IP
    "port": 5432,
    "dbname": "newbunyodkor",
    "user": "postgres",
    "password": "2222",
}

# Jadval nomi
TABLE_NAME = "contracts"

# JSON column nomi (sizda boshqacha bo'lishi mumkin)
# Masalan: contract_json, contract_data, data, payload, generated_data
JSON_COLUMN = "custom_fields"

# Excel file nomi
OUTPUT_FILE = "sportchilar_export.xlsx"


def safe_get(data, *keys, default=""):
    """
    Nested dict ichidan xavfsiz value olish.
    """
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
    return current if current is not None else default


def normalize_json_field(value):
    """
    Agar DB dan JSON string kelsa dictga aylantiradi.
    Agar dict bo'lsa o'zini qaytaradi.
    """
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}

    return {}


def main():
    conn = None
    try:
        # =========================
        # DB ulanish
        # =========================
        conn = psycopg2.connect(**DB_CONFIG)

        query = f"""
            SELECT id, {JSON_COLUMN}
            FROM {TABLE_NAME}
            WHERE status = 'ACTIVE'
            ORDER BY id;
        """

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()

        result = []

        for idx, row in enumerate(rows, start=1):
            contract_json = normalize_json_field(row.get(JSON_COLUMN))

            # JSON ichidan olish
            fio = safe_get(contract_json, "tarbiyalanuvchi", "fio", default="")
            guvohnoma = safe_get(contract_json, "tarbiyalanuvchi", "tugilganlik_guvohnoma", default="")
            tugilgan_sana = safe_get(contract_json, "tarbiyalanuvchi", "guvohnoma_qachon_bergan", default="")

            result.append({
                "№": idx,
                "Спортчилар исми шарифи": fio,
                "Паспорт маълумотлари": guvohnoma,
                "Туғилган сана": tugilgan_sana,
                "Бир спортчи учун белгиланган суғурта пули (сўм)": "",
                "Бир спортчи учун белгиланган суғурта мукофоти (сўм)": "",
            })

        # =========================
        # DataFrame yaratish
        # =========================
        df = pd.DataFrame(result)

        # =========================
        # Excelga yozish
        # =========================
        with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sportchilar")

            # Ustunlarni chiroyli qilish
            ws = writer.sheets["Sportchilar"]

            # Ustun kengliklari
            column_widths = {
                "A": 8,
                "B": 45,
                "C": 25,
                "D": 18,
                "E": 35,
                "F": 35,
            }

            for col, width in column_widths.items():
                ws.column_dimensions[col].width = width

        print(f"✅ Excel fayl yaratildi: {OUTPUT_FILE}")
        print(f"📄 Jami yozilgan qatorlar: {len(df)}")

    except Exception as e:
        print("❌ Xatolik yuz berdi:")
        print(str(e))

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()