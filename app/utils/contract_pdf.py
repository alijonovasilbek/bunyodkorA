from reportlab.lib.colors import black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import Image as RLImage
import json
import os
import sys
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from PyPDF2 import PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import tempfile
from PIL import Image
from io import BytesIO

# Try to find DejaVu fonts in common Linux locations
# font_locations = [
#     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
#     "/usr/share/fonts/dejavu/DejaVuSans.ttf",
#     "/usr/local/share/fonts/DejaVuSans.ttf",
#     r"C:\Users\Home\Downloads\dejavu-fonts-ttf-2.37\dejavu-fonts-ttf-2.37\ttf\DejaVuSans.ttf"  # Windows fallback
# ]
#
# bold_font_locations = [
#     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
#     "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
#     "/usr/local/share/fonts/DejaVuSans-Bold.ttf",
#     r"C:\Users\Home\Downloads\dejavu-fonts-ttf-2.37\dejavu-fonts-ttf-2.37\ttf\DejaVuSans-Bold.ttf"  # Windows fallback
# ]


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # -> app/
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

font_locations = [
    os.path.join(FONTS_DIR, "DejaVuSans.ttf"),
]

bold_font_locations = [
    os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf"),
]

# Find existing font files
font_path = None
bold_font_path = None

for path in font_locations:
    if os.path.exists(path):
        font_path = path
        break

for path in bold_font_locations:
    if os.path.exists(path):
        bold_font_path = path
        break
print("[OK] Normal font path:", font_path)
print("[OK] Bold font path:", bold_font_path)
# Shriftlarni ro'yxatdan o'tkazish logikasi
FONT_NORMAL = 'DejaVu'
FONT_BOLD = 'DejaVu-Bold'
FONT_FALLBACK = False

if font_path and bold_font_path:
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", font_path))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_font_path))
        FONT_NORMAL = 'DejaVu'
        FONT_BOLD = 'DejaVu-Bold'
        FONT_FALLBACK = False
    except Exception as e:
        print(f"!!! Shriftlarni ro'yxatdan o'tkazishda xato: {e}. Standart shriftlarga o'tildi.")
        FONT_FALLBACK = True
else:
    FONT_FALLBACK = True
    print(f"!!! DIQQAT: DejaVu shriftlari topilmadi. Standart shriftlar ishlatiladi.")
    print("!!! Hujjatda Kirill alifbosidagi matn xato (kvadratlar) chiqishi mumkin.")

registerFontFamily(
    'DejaVu',
    normal='DejaVu',
    bold='DejaVu-Bold',
    italic='DejaVu',
    boldItalic='DejaVu-Bold'
)

styles = getSampleStyleSheet()
for sname, s in styles.byName.items():
    s.fontName = FONT_NORMAL

# Optimized styles with reduced spacing to minimize page count
styles.add(
    ParagraphStyle(name='TitleUz', fontName=FONT_BOLD, fontSize=14, alignment=TA_CENTER, spaceAfter=3, leading=16))
styles.add(ParagraphStyle(name='SubtitleUz', fontName=FONT_NORMAL, fontSize=9, alignment=TA_CENTER, spaceAfter=8,
                          leading=11))
styles.add(ParagraphStyle(name='SectionHeaderUz', fontName=FONT_BOLD, fontSize=11, alignment=TA_CENTER, spaceAfter=5,
                          spaceBefore=8, leading=13))

styles.add(ParagraphStyle(name='NormalUz', fontName=FONT_NORMAL, fontSize=10, leading=13, alignment=TA_JUSTIFY,
                          firstLineIndent=15, spaceAfter=1))

styles.add(ParagraphStyle(name='ListItemUz', fontName=FONT_NORMAL, fontSize=10, leading=13, alignment=TA_JUSTIFY,
                          leftIndent=15, firstLineIndent=-15, spaceAfter=2))

styles.add(ParagraphStyle(name='AddressHeader', fontName=FONT_BOLD, fontSize=9, alignment=TA_LEFT, spaceAfter=5))
styles.add(ParagraphStyle(name='AddressDetail', fontName=FONT_NORMAL, fontSize=10, leading=12, spaceAfter=2))

styles.add(ParagraphStyle(
    name='SectionHeaderUzSpaced',
    parent=styles['SectionHeaderUz'],
    spaceBefore=12
))

styles.add(ParagraphStyle(
    name='UnderlineField',
    parent=styles['NormalUz'],
    fontName=FONT_BOLD,
    fontSize=10,
    leading=11,
    spaceAfter=0,
    firstLineIndent=0,
))

styles.add(ParagraphStyle(
    name='SmallCenter',
    fontName=FONT_NORMAL,
    fontSize=8,
    alignment=TA_CENTER,
    leading=9,
    spaceAfter=3
))

styles.add(ParagraphStyle(
    name='SmallText',
    parent=styles['Normal'],
    fontName=FONT_NORMAL,
    fontSize=8,
    leading=9,
    alignment=TA_CENTER,
    spaceAfter=8
))

styles.add(ParagraphStyle(
    name='NormalUzNoIndent',
    parent=styles['NormalUz'],
    firstLineIndent=0,
    alignment=TA_JUSTIFY,
    spaceAfter=6
))


class ContractPDFGenerator:
    """Platypus yordamida shartnoma yaratuvchi sinf"""

    def __init__(self, data_file_or_dict):
        """
        Konstruktor - ma'lumotlarni yuklash

        Args:
            data_file_or_dict: JSON fayl yo'li yoki dictionary
        """
        self.data = self._load_data(data_file_or_dict)
        self.story = []
        self.doc = SimpleDocTemplate(
            "FK_Bunyodkor_Shartnoma.pdf",
            pagesize=A4,
            leftMargin=12 * mm,  # Reduced from 15mm
            rightMargin=12 * mm,  # Reduced from 15mm
            topMargin=8 * mm,    # Reduced from 10mm
            bottomMargin=15 * mm  # Reduced from 25mm
        )
        self.doc.width = A4[0] - self.doc.leftMargin - self.doc.rightMargin
        self.logo_filename = "Bunyodkor-new.png"
        self.render_text_content = bool(self.data.get("render_text_content", False))

    def _add_underlined_multiline_text(self, text, style, line_width=0.5):
        from reportlab.pdfbase.pdfmetrics import stringWidth

        max_width = self.doc.width
        words = text.split()
        lines = []
        current = ""

        for word in words:
            test = (current + " " + word).strip()
            if stringWidth(test, style.fontName, style.fontSize) <= max_width:
                current = test
            else:
                lines.append(current)
                current = word

        if current:
            lines.append(current)

        flowables = []

        for line in lines:
            p = Paragraph(line, style)
            flowables.append(p)

            table = Table(
                [[""]],
                colWidths=[max_width]
            )
            table.setStyle(TableStyle([
                ('LINEBELOW', (0, 0), (0, 0), line_width, black),
                ('TOPPADDING', (0, 0), (0, 0), -4),
                ('BOTTOMPADDING', (0, 0), (0, 0), 0),
                ('LEFTPADDING', (0, 0), (0, 0), 0),
                ('RIGHTPADDING', (0, 0), (0, 0), 0),
            ]))

            flowables.append(table)

        return flowables

    def _load_data(self, data_file_or_dict):
        """
        Ma'lumotlarni JSON fayldan yuklash yoki dictionary sifatida qabul qilish

        Args:
            data_file_or_dict: JSON fayl yo'li (str) yoki dictionary

        Returns:
            dict: Shartnoma ma'lumotlari
        """
        if isinstance(data_file_or_dict, dict):
            print("Ma'lumotlar dictionary sifatida qabul qilindi")
            return data_file_or_dict

        if os.path.exists(data_file_or_dict):
            print(f"Ma'lumotlar fayli yuklanmoqda: {data_file_or_dict}")
            with open(data_file_or_dict, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            default_data = self._default_template()
            with open(data_file_or_dict, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4, ensure_ascii=False)
            print(f"!!! Xato: Ma'lumotlar fayli topilmadi: {data_file_or_dict}")
            print(f"  Namuna '{data_file_or_dict}' fayli yaratildi. Uni tahrirlab, keyin ishga tushiring.")
            sys.exit(1)

    def _default_template(self):
        """Default template ma'lumotlari (agar JSON topilmasa)"""
        return {

            "shartnoma_raqami": "N0012025",
            "student": {
                "student_image": "student_photo.png",
                "student_fio": "Юсупов Абдулборий Баҳодирович",
                "birth_year": "2012",
                "student_address": "Тошкент ш. Чилонзор т. Лутфий кўчаси 61-уй",
                "dad_occupation": "Тадбиркор",
                "mom_occupation": "Уй бекаси",
                "dad_phone_number": "(33) 135-80-09",
                "mom_phone_number": "(78) 162-16-14",
                "mom_fullname": "Бахриддинова Гулова Баҳромовна"
            },
            "sana": {
                "kun": "06",
                "oy": "Декабр",
                "yil": "2025"
            },
            "buyurtmachi": {
                "fio": "Юсупов Абдулборий Баҳодирович",
                "pasport_seriya": "AA 1234567",
                "pasport_kim_bergan": "Тошкент ш. Чилонзор т. ИИББ бўлими",
                "pasport_qachon_bergan": "15.03.2018",
                "manzil": "Тошкент ш., Чилонзор тумани, Лутфий кўчаси 61-уй",
                "telefon": "+998 (33) 135-80-09"
            },
            "tarbiyalanuvchi": {
                "fio": "Юсупов Абдулборий Баҳодирович",
                "tugilganlik_guvohnoma": "I-AA 9876543",
                "tugilganlik_yil": 2011,
                "guvohnoma_kim_bergan": "Тошкент ш. ФҲБ Чилонзор т. бўлими",
                "guvohnoma_qachon_bergan": "12.04.2012"
            },
            "shartnoma_muddati": {
                "boshlanish": "«01» Январ",
                "tugash": "«31» Декабр",
                "yil": "2025"
            },
        }

    def _add_underlined_field(self, label, value="", line_length=80, after_space=3):
        """Label + pastida chiziq chizilgan qiymat (agar qiymat bo'sh bo'lsa, chiziq baribir chiqadi)"""
        from reportlab.platypus import Table, TableStyle, Paragraph
        from reportlab.lib.colors import black

        if not value:
            display_value = ""
        else:
            display_value = value

        table = Table(
            [[Paragraph(f"{label} {display_value}", styles['NormalUz'])]],
            colWidths=[self.doc.width]
        )
        table.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        self.story.append(table)
        self._add_spacer(after_space)


    def _add_ariza_page(self):
        data = self.data
        student = data.get("student", {})
        buyurtmachi = data.get("buyurtmachi", {})
        shartnoma_raqami = data.get("shartnoma_raqami", "")

        img_path = student.get("student_image")

        if img_path:
            try:
                if img_path.startswith("http"):
                    import httpx
                    from io import BytesIO
                    response = httpx.get(img_path, timeout=10.0)
                    response.raise_for_status()
                    img_bytes = BytesIO(response.content)
                    left_block = RLImage(img_bytes, width=30 * mm, height=40 * mm)
                elif os.path.exists(img_path):
                    left_block = RLImage(img_path, width=30 * mm, height=40 * mm)
                else:
                    left_block = Paragraph("[Rasm topilmadi]", ParagraphStyle(
                        name='PlaceholderStyle',
                        fontSize=8,
                        alignment=TA_CENTER
                    ))
            except Exception as e:
                print(f"[WARN] Rasm yuklashda xato: {e}")
                left_block = Paragraph("[Rasm yuklab bo'lmadi]", ParagraphStyle(
                    name='PlaceholderStyle',
                    fontSize=8,
                    alignment=TA_CENTER
                ))
        else:
            left_block = Paragraph("[Rasm yo'q]", ParagraphStyle(
                name='PlaceholderStyle',
                fontSize=8,
                alignment=TA_CENTER
            ))

        right_style = ParagraphStyle(
            name='DirectorInfo',
            parent=styles['NormalUz'],
            fontSize=11,
            alignment=TA_RIGHT,
            leading=14
        )
        right_text = (
            "«BUNYODKOR» ФА<br/>"
            "Директорига<br/>"
            "<b>Ш.Н.Саидовга</b>"
        )
        right_block = Paragraph(right_text, right_style)

        top_table = Table(
            [[left_block, right_block]],
            colWidths=[45 * mm, self.doc.width - 45 * mm]
        )
        top_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        self.story.append(top_table)
        self._add_spacer(4)

        self.story.append(Paragraph("<b>Ариза</b>", styles['TitleUz']))
        self._add_spacer(2)

        student_fio = student.get("student_fio", "")
        student_birth_year = student.get("birth_year", "20__")
        student_address = student.get("student_address", "")
        dad_job = student.get("dad_occupation", "")
        mom_job = student.get("mom_occupation", "")
        dad_phone = student.get("dad_phone_number", "")
        mom_phone = student.get("mom_phone_number", "")
        momordad_fio = buyurtmachi.get("fio", "")

        left_indent_mm = 10

        self.story.append(Paragraph(
            f"Ушбу ариза билан Сиздан, <b>{student_birth_year}</b> йилда туғилган фарзандим (Ф.И.Ш.):",
            ParagraphStyle(
                name='UshbuIndented',
                parent=styles['NormalUzNoIndent'],
                leftIndent=20
            )
        ))

        fio_table = Table(
            [[
                Paragraph(f"<b>{student_fio or '_____________________________________'}</b>", styles['NormalUz']),
                Paragraph("ни,", styles['NormalUz'])
            ]],
            colWidths=[self.doc.width - (left_indent_mm + 25 * mm), 15 * mm]
        )

        fio_table.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (0, 0), 0.7, black),
            ('LEFTPADDING', (0, 0), (0, 0),0),
            ('LEFTPADDING', (1, 0), (1, 0), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ]))
        self.story.append(fio_table)
        self._add_spacer(2)

        address_table = Table(
            [[Paragraph(f"<b>{student_address or '_____________________________________'}</b>", styles['NormalUz'])]],
            colWidths=[self.doc.width - (left_indent_mm + 10 * mm), 10 * mm]
        )

        address_table.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -1), 0.7, black),
            ('LEFTPADDING', (0, 0), (-1, -1), left_indent_mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        self.story.append(address_table)

        self.story.append(Paragraph(
            f"<para leftIndent={left_indent_mm}>(вилоят, шаҳар, туман, кўча, уй рақами, хонадон)</para>",
            ParagraphStyle(
                name='HintBelowAddr',
                fontName=FONT_NORMAL,
                fontSize=10,
                textColor=colors.grey,
                alignment=TA_LEFT
            )
        ))
        self._add_spacer(2)
        self.story.append(Paragraph(
            f"<para leftIndent={left_indent_mm}>манзилида яшовчи, «BUNYODKOR» ФК МЧЖ болалар-ўсмирлар футбол Академиясининг тўловли таълим гуруҳига қабул қилишингизни сўрайман.</para>",
            styles['NormalUzNoIndent']
        ))
        self._add_spacer(4)

        occupation_style = ParagraphStyle(
            name='OccupationStyle',
            fontName=FONT_NORMAL,
            fontSize=11,
            leading=14
        )
        table_data = [
            [
                Paragraph("Ота касби (лавозими):", occupation_style),
                Paragraph(dad_job or "_________", occupation_style),
                Paragraph("Тел:", occupation_style),
                Paragraph(dad_phone or "_________", occupation_style)
            ],
            [
                Paragraph("Она касби (лавозими):", occupation_style),
                Paragraph(mom_job or "_________", occupation_style),
                Paragraph("Тел:", occupation_style),
                Paragraph(mom_phone or "_________", occupation_style)
            ]
        ]
        parent_table = Table(table_data, colWidths=[50 * mm, 60 * mm, 15 * mm, 45 * mm])
        parent_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NORMAL),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        self.story.append(parent_table)
        self._add_spacer(6)

        self.story.append(Paragraph("<b>ОТА-ОНАСИНИНГ МАЖБУРИЯТЛАРИ:</b>", styles['SectionHeaderUz']))
        self._add_spacer(2)

        majburiyat_text = (
            f"Биз, (боланинг ота-онаси) (<u><b>{momordad_fio}</b></u>), "
            "фарзандимизнинг мазкур Академияда шуғулланиши учун ҳар ойлик хизмат ҳақини ўз вақтида тўлаш мажбуриятини оламиз."
        )

        self.story.append(Paragraph(majburiyat_text, styles['NormalUzNoIndent']))
        self._add_spacer(6)

        imzo_table = Table([
            ["Ота-она (Ф.И.Ш.)", "", "Имзо"],
            [f"{momordad_fio}", "", "__________"]
        ], colWidths=[80 * mm, 20 * mm, 40 * mm])
        imzo_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NORMAL),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (2, 0), (2, -1), "CENTER"),
        ]))
        self.story.append(imzo_table)
        self._add_spacer(70)

        shartnoma_raqam_style = ParagraphStyle(
            name='ShartnomanRaqam',
            fontName=FONT_BOLD,
            fontSize=11,
            alignment=TA_CENTER,
            leading=14
        )

        self.story.append(Paragraph(
            shartnoma_raqami,
            shartnoma_raqam_style
        ))

        self.story.append(PageBreak())


    def _add_spacer(self, height=5):
        """Bo'shliq qo'shish"""
        self.story.append(Spacer(1, height * mm))

    def _add_spacer_return(self, height=5):
        """Flowable sifatida qaytariladigan spacer (jadval ichida ishlashi uchun)"""
        return Spacer(1, height * mm)

    def _add_logo(self):
        """Logotipni (rasmni) hujjat tepasiga qo'shish"""
        if os.path.exists(self.logo_filename):
            logo = RLImage(self.logo_filename, width=15 * mm, height=15 * mm)

            logo.hAlign = 'CENTER'

            self.story.append(logo)

            self._add_spacer(1)

            self.story.append(Table([['']], colWidths=[self.doc.width], style=TableStyle([
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
            ])))
            self._add_spacer(1)
        else:
            print(f"!!! DIQQAT: Logotip fayli topilmadi: {self.logo_filename}. Sarlavha oddiy matn bilan davom etadi.")

    def _add_header(self):
        """Shartnoma boshi (sarlavha, sana, joy)"""
        data = self.data

        self._add_logo()

        self.story.append(Paragraph(
            f"Шартнома №{data.get('shartnoma_raqami', '______')}",
            styles['TitleUz']
        ))
        self.story.append(Paragraph(
            "(Пуллик жисмоний тарбия ва спорт хизматларини кўрсатиш бўйича)",
            styles['SubtitleUz']
        ))

        sana = data.get('sana', {})
        sana_text = f'«{sana.get("kun", "___")}» {sana.get("oy", "___________")} {sana.get("yil", "___")} й.'

        col_widths = [self.doc.width - 50 * mm, 50 * mm]

        header_table_data = [
            [
                Paragraph("Тошкент ш.",
                          ParagraphStyle(name='HLeft', fontName=FONT_NORMAL, fontSize=11, alignment=TA_LEFT)),
                Paragraph(sana_text,
                          ParagraphStyle(name='HRight', fontName=FONT_NORMAL, fontSize=11, alignment=TA_RIGHT))
            ]
        ]

        header_table = Table(header_table_data, colWidths=col_widths)
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        self.story.append(header_table)
        self._add_spacer(4)

    def _add_parties_info(self):
        """Tomonlar va Tarbiyalanuvchi ma'lumotlari"""
        data = self.data
        buyurtmachi = data.get('buyurtmachi', {})
        tarbiya = data.get('tarbiyalanuvchi', {})

        text1 = """<b>«FK BUNYODKOR» МЧЖ Тошкент шаҳар филиали</b> бундан буён «Ижрочи» деб юритиладиган, ишончнома асосида фаолият юритаётган Директор Ш.Н.Саидов, бир томондан ва бундан буён «Буюртмачи» деб юритиладиган """
        self.story.append(Paragraph(text1, styles['NormalUz']))

        fio_buyurtmachi = buyurtmachi.get('fio', '________________________________')
        pasport_seriya = buyurtmachi.get('pasport_seriya', 'AA ________')
        pasport_kim_bergan = buyurtmachi.get('pasport_kim_bergan', '________________________________')
        pasport_qachon_bergan = buyurtmachi.get('pasport_qachon_bergan', '___.___._____')

        buyurtmachi_text = (
            f"{fio_buyurtmachi},  "
            f"{pasport_seriya},  "
            f"{pasport_kim_bergan},  "
            f"{pasport_qachon_bergan} "
        )

        elements = self._add_underlined_multiline_text(
            buyurtmachi_text,
            ParagraphStyle(
                name='UnderlineBold',
                parent=styles['UnderlineField'],
                fontName=FONT_BOLD
            )
        )
        self.story.extend(elements)

        self.story.append(Paragraph(
            "(фуқаронинг Ф.И.Ш, паспорт серияси, ким томонидан ва қачон берилган)",
            styles['SmallText']
        ))

        text2 = "бошқа томондан, ушбу шартномани қўйидагилар тўғрисида туздилар:"
        self.story.append(Paragraph(text2, styles['NormalUzNoIndent']))

        text3 = "Тарбияланувчининг туғилганлик тўғрисидаги гувоҳномаси:"
        self.story.append(Paragraph(text3, styles['NormalUzNoIndent']))

        fio_tarbiya = tarbiya.get('fio', '________________________________')
        guvohnoma = tarbiya.get('tugilganlik_guvohnoma', 'I-AA _________')
        guvohnoma_kim_bergan = tarbiya.get('guvohnoma_kim_bergan', '________________________________')
        guvohnoma_qachon_bergan = tarbiya.get('guvohnoma_qachon_bergan', '___.___._____')

        tarbiya_text = (
            f"{fio_tarbiya},  "
            f"{guvohnoma},  "
            f"{guvohnoma_kim_bergan},  "
            f"{guvohnoma_qachon_bergan}"
        )

        elements = self._add_underlined_multiline_text(tarbiya_text, styles['UnderlineField'])
        self.story.extend(elements)

        self.story.append(Paragraph(
            "(Ф.И.Ш, серияси, ким томонидан ва қачон берилган)",
            styles['SmallText']
        ))

    def _add_section(self, num, title, paragraphs, is_list=False, header_style='SectionHeaderUz'):
        """Bo'lim sarlavhasi va matnini qo'shish"""

        self.story.append(Paragraph(f"{num}. {title}", styles[header_style]))

        for p in paragraphs:
            if is_list:
                self.story.append(Paragraph(p, styles['ListItemUz']))
            else:
                self.story.append(Paragraph(p, styles['NormalUz']))

    def _add_signature_block(self):
        # self._add_spacer(55)
        """11. Yuridik manzillar va imzolar"""
        self.story.append(Paragraph(
            "11. ЮРИДИК МАНЗИЛЛАР ВА БАНК РЕКВИЗИТЛАРИ",
            styles['SectionHeaderUz']
        ))
        self._add_spacer(2)

        buyurtmachi = self.data.get('buyurtmachi', {})

        ijrochi_text = """
        <b>« Ижрочи »</b><br/>
        <b>« FK BUNYODKOR » МЧЖ</b><br/>
        Тошкент шаҳар филиали<br/><br/>
        Тошкент шаҳар, Чилонзор тумани,<br/>
        Бунёдкор шох кўчаси, 47-уй.<br/><br/>
        ҳ/р 2020 8000 9044 2411 1005<br/>
        ЎзСҚБ АТБ Тошкент шаҳар Бош офиси<br/>
        МФО: 00440, СТИР: 205 737 924, ОКЭД: 93110<br/>
        Тел/факс: 71-230-40-01<br/><br/><br/>
        <b>Директор</b>       Ш.Н.Саидов<br/><br/>
        _______________________<br/>
        М.Ў.
        """
        P_ijrochi = Paragraph(ijrochi_text, styles['AddressDetail'])

        def underline_row(text):
            t = Table([[Paragraph(text, styles['AddressDetail'])]],
                      colWidths=[self.doc.width / 2 - 20])
            t.setStyle(TableStyle([
                ('LINEBELOW', (0, 0), (-1, -1), 0.8, black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
            ]))
            return t

        fio = buyurtmachi.get("fio", "")
        pasport = buyurtmachi.get("pasport_seriya", "")
        kim_bergan = buyurtmachi.get("pasport_kim_bergan", "")
        qachon_bergan = buyurtmachi.get("pasport_qachon_bergan", "")
        manzil = buyurtmachi.get("manzil", "")
        telefon = buyurtmachi.get("telefon", "")

        right_block = [
            Paragraph("<b>«Буюртмачи»</b>", styles['AddressDetail']),
            Paragraph("«Ота ёки Она»", styles['AddressDetail']),
            self._add_spacer_return(6),
            underline_row(fio),
            Paragraph("(фамилия, исм, отасининг исми)", styles['SmallCenter']),
            self._add_spacer_return(4),

            underline_row("Паспорт № " + pasport),
            underline_row("Берилган: " + kim_bergan),
            underline_row(qachon_bergan),
            underline_row("Манзил: " + manzil),
            underline_row("Телефон: " + telefon),
            self._add_spacer_return(8),
            underline_row("Имзо")
        ]

        right_flow = []
        for item in right_block:
            if item is None:
                continue
            right_flow.append(item)

        signature_table = Table(
            [[P_ijrochi, right_flow]],
            colWidths=[self.doc.width / 2, self.doc.width / 2]
        )

        signature_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), "TOP"),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 15),
            ('LEFTPADDING', (1, 0), (1, 0), 15),
            ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ]))

        self.story.append(KeepTogether(signature_table))

    def get_flowables(self):
        """Barcha PDF elementlarini (Flowables) tayyorlash"""
        self.story = []

        if not self.render_text_content:
            return self.story

        self._add_ariza_page()

        self._add_header()
        self._add_parties_info()

        section1 = [
            "Мазкур шартноманинг предмети <b>Ижрочи</b> томонидан <b>Буюртмачига</b> пуллик жисмоний тарбия ва спорт хизматларини (футбол курси) кўрсатиш ҳисобланади.",
            "«FK BUNYODKOR» МЧЖ Тошкент шаҳар филиали ички тартиб қоидаларига мувофиқ пуллик жисмоний тарбия ва спорт хизматларини (футбол курси) кўрсатиш бўйича шартномалар ҳар ойнинг 25-санасидан бошлаб, кейинги ойнинг 5-санасига қадар имзоланиши ва мазкур шартноманинг 6.1-бандига мувофиқ тўлов тўлангандан сўнг ўқув-машғулотлар бошлашга рухсат берилиши маълумот учун қабул қилинади."
        ]
        self._add_section("1", "Шартнома предмети", section1)

        section2_1 = [
            "<b>2.1. Ижрочи қуйидаги мажбуриятларни ўз зиммасига олади:</b>",
            "<b>2.1.1.</b> Машғулотларни тасдиқланган график асосида олиб бориш;",
            "<b>2.1.2.</b> Буюртмачини машғулотларни олиб бориш бўйича зарурий ахборот билан таъминлаш;",
            "<b>2.1.3.</b> Машғулотларни олиб бориш бўйича зарур шароитни яратиб бериш;",
            "<b>2.1.4.</b> «ФК Бунёдкор» Футбол академиясида жисмоний тарбия ва спорт тадбирларини ўтказишда техника хавфсизлиги бўйича кириш ва жорий инструктаж олиб бориш;",
            "<b>2.1.5.</b> Тарбияланувчининг максимал спорт натижаларига эришиш учун унинг имкониятларини кенгайтиришга шароитлар яратиш, унинг спорт маҳоратини оширишда замонавий техника воситаларидан фойдаланиш;",
            "<b>2.1.6.</b> Ўз вақтида хизматларни кўрсатишнинг ўзгариши тўғрисида Буюртмачини хабардор қилиш;",
            "<b>2.1.7.</b> Ўтказиладиган спорт машғулотлари дастури ва жадвалига мувофиқ мураббий (лар) бошчилигида машғулотларни ўтказишни сифатли ва тўлиқ таъминлаш. Ижрочи жамоага мураббий (лар)ни мустақил равишда алмаштириш, тайинлаш ҳуқуқини ўзида сақлаб қолади.",
             "<b>2.1.8.</b> Тарбияланувчини Академия ҳудудидаги спорт машғулотлари ва расмий ўйин вақтида содир бўладиган бахтсиз ҳодисалардан мажбурий суғурта қилиш."
        ]
        section2_2 = [
            "<b>2.2. Ижрочи қуйидагиларга ҳақли:</b>",
            "<b>2.2.1.</b> Шартнома муддати тугаши билан янги муддатга шартнома тузишдан бош тортиш, агар Буюртмачи амалдаги шартнома муддати давомида ушбу шартномада (тўлов муддати, соғлиғи ва ички тартиб қоидаларни бузиш ҳоллари) ва фуқаролик қонунчилигида белгиланган қоидабузарликларни содир қилса;",
            "<b>2.2.2.</b> Агар <b>Буюртмачи</b> ўз хоҳишига кўра спорт-машғулотларга қатнашишни тўхтатса, шунингдек, Ички тартиб қоидаларни мунтазам равишда бузиб келган бўлса, келиб тушган тўловларни қайтармайди. Бунда, Буюртмачи томонидан шартномнинг 6.1-бандига мувофиқ келиб тушган маблағлар ҳам қайтарилмаслиги инобатга олинади;",
            "<b>2.2.3.</b> <b>Ижрочи</b> бир томонлама шартнома шартларига ўзгартириш киритиш ҳуқуқига эга, хусусан, хизматлар нархини ўзгартириш масаласида (коммунал тўловлар нархининг ўсиши ва х.к.). Шартнома шартларининг ўзгариши тўғрисида Буюртмачи ўн кун олдин оғзаки ёки ёзма тарзда огоҳлантирилади.  Бунда мазкур огоҳлантириш алоқанинг ҳар қандай воситаси ёрдамида етказилиши мумкин;",
            """<b>2.2.4.</b> Агар <b>Буюртмачи</b> шартноманинг амал қилиш мудати давомида ўз хоҳишига кўра узрли сабабларсиз спорт машғулотларга қатнашишни 15 кундан ортиқ тўхтатиб, кейинги ойдан бошлаб спорт-машғулотларга қатнашиш истагини <b>Ижрочига</b> қайта билдирса, <b>Ижрочи</b> спорт-машғулотларга келинмаган кунлар учун ҳам тегишли тўловни талаб қилишга ҳақли. Бунда, <b>Буюртмачи</b> томонидан мазкур талаб қилинаётган тўловларни тўламаслик мазкур шартномани Ижрочи томонидан хизмат кўрсатилиши тўхташига ва шартномани бекор қилинишига олиб келади""",
            "<b>2.2.5.</b> Ижрочи ўз тарбияланувчилари (ОАВ, Интернетда) ҳақидаги маълумотларни тарқатишда ва буюртмачи билан профессионал футболда янада ривожлантириш масаласини ҳал қилишда имтиёзли ҳуқуққа эга;",
            "<b>2.2.6.</b> Ижрочи ота-она (қонуний вакил)лар билан келишилган ҳолда спорт тадбирларини қисман молиялаштириш учун тарбияланувчининг ота-она маблағларини, шунингдек қонуний вакиллар маблағларини жалб қилиш ва фойдаланишга ҳақли;",
            "<b>2.2.7.</b> Мазкур шартнома бўйича кўрсатиладиган хизматларнинг амалга оширилиши бўйича маълумотлар берилишини талаб қилиш."
           
        ]
        self._add_section("2", "Ижрочининг ҳуқуқ ва мажбуриятлари", section2_1 + section2_2, is_list=True)

        # section3_1 = [
        #     "<b>3.1. Буюртмачи қуйидагиларга ҳақли:</b>",
        #     "<b>3.1.1.</b> Мазкур шартнома бўйича кўрсатиладиган хизматларнинг амалга оширилиши бўйича маълумотлар берилишини талаб қилиш;",
        #     "<b>3.1.2.</b> Жисмоний тарбия ва спорт хизматларини кўрсатиш учун зарур бўлган Ижрочининг мулкидан фойдаланиш;",
        #     "<b>3.1.3.</b> Ижрочи фаолиятини тартибга солувчи ҳужжатлар (Низом, спорт машғулотлари жадвали ва бошқалар) билан танишиш;",
        #     "<b>3.1.4.</b> Мазкур шартномада белгиланган муддатларда Ижрочига ёзма хабар юбориш орқали хизматлардан фойдаланишдан бош тортиш."
        # ]
        section3_2 = [
            "<b>3.2. Буюртмачи қуйидаги мажбуриятларни ўз зиммасига олади:</b>",
            "<b>3.2.1.</b> Тиббий маълумотномани ўз вақтида тақдим этиш;",
            "<b>3.2.2.</b> Машғулотларни тўхтатиш бўйича оқилона муддат давомида Ижрочини хабардор қилиш;",
            "<b>3.2.3.</b> Машғулотларга белгиланган спорт экипировкасида келиш;",
            "<b>3.2.4.</b> Ўзбекистон Республикасининг амалдаги қонунчилик ҳужжатларига мувофиқ Ижрочига тегишли мол-мулкка етказилган зарарни қоплаб бериш;",
            "<b>3.2.5.</b> Футбол клуби раҳбарияти ҳамда БЎФА тренерлари ваколат доирасига кирувчи салаларга аралашмаслик, жумладан, спорт-машғулот жараёнини ташкил этиш ва ўтказиш ишларига, футбол ўйинининг тактик режаси, шунингдек сафарлар, учрашувлар ва ҳакозоларнинг умумий режасига таъллуқли кўрсатмаларга ҳамда Клуб (БЎФА) обрўсига путур етказишга ҳаракатлар тўғрисида хабар бериб туриш;",
            "<b>3.2.6.</b> \"ФК Бунёдкор\" МЧЖ Тошкент шаҳри филиали (болалар ва ўсмирлар футбол академияси)да тарбияланаётган ёш футболчилар ота-оналарининг аҳлоқ қоидаси\"ва академиянинг бошқа локал ҳужжатлари нормаларига тўлиқ ва сўзсиз амал қилиш."
        ]
        section3_3 = [
            "<b>3.3. Буюртмачи қуйидагиларга ҳақли:</b>",
            "<b>3.3.1.</b> Мазкур шартнома бўйича кўрсатиладиган хизматларнинг амалга оширилиши бўйича маълумотлар берилишини талаб қилиш;",
            "<b>3.3.2.</b> Жисмоний тарбия ва спорт хизматларини кўрсатиш учун зарур бўлган Ижрочининг мулкидан фойдаланиш: машқлар даврида тренажер залидан ва машқлардан сўнг душ (ювиниш) хонасидан;",
            "<b>3.3.3.</b> Ижрочи фаолиятини тартибга солувчи ҳужжатлар (Низом, спорт машғулотлари жадвали ва бошқалар) билан танишиш;",
            "<b>3.3.4.</b> Мазкур шартномада белгиланган муддатларда Ижрочига ёзма хабар юбориш орқали хизматлардан фойдаланишдан бош тортиш;",
            "<b>3.3.5.</b> Мазкур шартнома бўйича кўрсатиладиган хизматларнинг амалга оширилиши бўйича маълумотлар берилишини талаб қилиш (+998990245246 телефон рақамидан Академиянинг маркетинг-тижорат бўлими юборган барча хабарлар расмий бўлиб ҳисобланади);",
            "<b>3.3.6.</b> Жисмоний тарбия ва спорт хизматларини кўрсатиш учун зарур бўлган Ижрочининг мулкидан фойдаланиш."
        ]
        section3_4 = [
            "<b>3.4. Буюртмачи, тарбияланувчининг мажбуриятлари:</b>",
            "<b>3.4.1.</b> Мазкур шартноманинг амал қилиш муддати тугагунга қадар бошқа спорт мактаби (секция, академия), спорт мактаб-интернати, профессионал ёки ҳаваскор футбол клуби (шу жумладан селекционерлар) билан ушбу шартномага ўхшаш шартнома (контракт) тузмаслик;",
            "<b>3.4.2.</b> Тарбияланувчини машғулотлар жараёнида бошқа спорт мактаби (секция, академия), спорт мактаб-интернати, профессионал ёки ҳаваскор футбол клубга юбормайди."
        ]

        self._add_section(
            "3",
            "Буюртмачи, тарбияланувчининг ҳуқуқ ва мажбуриятлари",
             section3_2 + section3_3 + section3_4,
            is_list=True,
            header_style='SectionHeaderUzSpaced'
        )

        muddat = self.data.get('shartnoma_muddati', {})
        section4 = [
            f"Мазкур шартнома «{muddat.get('boshlanish', '___')}» {muddat.get('yil', '2025')} йилдан {muddat.get('yil', '2025')} йил «{muddat.get('tugash', '31')}» декабрга қадар амал қилади."
        ]
        self._add_section("4", "Шартноманинг амал қилиш муддати", section4, is_list=False)

        section5 = [
            "<b>5.1.</b> Томонларнинг ҳеч бири ушбу шартноманинг ҳар қандай бузилиши учун жавобгар бўлмайди, агар бу тўғридан-тўғри ёки билвосита томонлар назоратидан ташқари бўлган табиий ҳодисалар натижасида келиб чиққан бўлса, шу жумладан ҳарбий ҳаракатлар, ҳукумат қарорлари, ёнғин, карантин, тошқин ёки изоҳлаб бўлмайдиган табиий ҳодисалар."
        ]
        self._add_section("5", "Форс-мажор", section5, is_list=False)

        narx_html = "<u><b>___</b></u>"

        section6 = [
            f"<b>6.1.</b> Абонементнинг ойлик тўлов нархи ҚҚСсиз {narx_html} сўмни ташкил қилади.",

            """<b>6.2.</b> Ушбу шартнома бўйича тўлов спорт-машғулот бошланишига қадар 100% миқдорида ҳар ойнинг 1 (биринчи) санасидан 10 (ўнинчи) санасига қадар пул кўчириш ёки пластик карта орқали клубга хизмат кўрсатадиган банкдаги ҳисоб рақамига ўтказган ҳолда амалга оширилади. Мазкур бандда келтирилган тартибда тўловлар амалга оширилганда тўлов топшириқномаларини тўғри тўлдириш ва Ижрочига ўз вақтида топшириш Буюртмачи зиммасига юклатилади. Тўғри тўлдирилмаган ёки Ижрочига ўз вақтида топширилмаган тўлов топшириқномалари бўйича тўловлар Буюртмачи томонидан мазкур шартноманинг рўйхатга олинган рақами бўйича қабул қилинади.""",

            f"""<b>6.3.</b> Ота-оналар бир марталик {narx_html} сўмни олдиндан тўловини амалга оширадилар, ушбу тўлов тарбияланувчининг ўқишга келишини ва ота-оналарнинг тўловларни мунтазам (ўз вақтида) амалга ошириш ниятларининг кафолатидир. Ушбу тўлов орқали шартноманинг сўнги ойи тўлови ёпилади. Агар Буюртмачи шартномани муддатидан аввал сабабсиз бекор қилса, ушбу тўлов қайтарилмайди. Ушбу тўлов ота-оналар академия раҳбариятига ариза ёзиб, асосли ҳужжатларни (соғлиғи, яшаш жойи ўзгариши) тақдим этганда қайтарилиши мумкин."""
        ]

        self._add_section("6", "Тўлов қилиш тартиби", section6, is_list=True)

        # --- 7-10 Bo'limlar ---
        section7 = [
            "<b>7.1.</b>Шартнома доирасида ўз мажбуриятларини бажариш қисми сифатида, томонлар амалдаги қонун талабларига мувофиқликни таъминлаш, шу жумладан, коррупцияга қарши кураш бўйича қабул қилинган қонунга риоя этиш, улар, уларнинг ходимлари, филиаллари, бенефициар ва бизнес ҳамкорлар, воситачилар, пудратчилар ёки агентлар шартнома бажаришда пул бериш ёки пора сифатида қабул қилиш, тижорат порахўрлиги, порахўрликда воситачилик, давлат органи, давлат ҳиссаси иштирокидаги ташкилотлар ёки фуқароларнинг ўзини ўзи бошқариш органлари ходимларига пул таклиф қилиш ва ушбу шартнома ҳамда коррупцияга қарши кураш бўйича халқаро актлар ва жиноятчиликдан тушган тушумларни легаллаштириш (ўз ҳисобига ноқонуний равишда ўтқазиш) ва терроризмни молиялаштириш мақсадлари учун амалдаги қонун ҳужжатларида назарда тутилган бошқа ҳуқуқбузарликлар каби ишларни (ёки ҳеч нарса қилмасликдан бўйин товлаш) амалга оширмайдилар.",
            "<b>7.2.</b>Тарафлар тўғридан-тўғри ёки билвосита шахсан ёки учинчи шахслар орқали, таклиф, ваъда, пора, талаб, пул қабул қилиш учун розилик, бошқа бойликлар, мулк, мулк ҳуқуқлари ёки бошқа моддий ва/ёки номоддий манфаат йўлида ёки бирон шахс томонидан ноҳақ фойда олиш учун тарафлар ўртасидаги муносабатлардан фойдаланиб, ошкоралик ва очиқлик тамойилларига қарши равишда, шу жумладан, бошқа ноқонуний мақсадларга эришиш учун уларга таъсир кўрсатиш. Томонлар ушбу ҳаракатларнинг олдини олиш бўйича барча чора-тадбирларни кўришни кафолатлайди."
        ]
        self._add_spacer(4)
        self._add_section("7", "Коррупцияга қарши қоидалар", section7, is_list=False)

        section8 = [
            "<b>8.1.</b>Мазкур шартнома шартларини бузганлик фактлари аниқланса, айбдор томон амалдаги Ўзбекистон Республикаси қонунчилик ҳужжатларида, жумладан Фуқаролик кодекси ҳамда \"Хўжалик юритувчи субъектлар фаолиятининг шартномавий-ҳуқуқий базаси тўғрисида\"ги қонунда белгиланган тартибда шартнома мажбуриятларини бажармаганлик учун жавобгар бўлади."
        ]
        self._add_section("8", "Тарафларнинг жавобгарлиги", section8, is_list=False)

        section9_elements = []
        section9_elements.append(Paragraph(
            "9. Низоларни ҳал этиш тартиби",
            styles['SectionHeaderUzSpaced']
        ))
        section9_elements.append(Paragraph(
            "<b>9.1.</b>Ушбу шартномани ижро қилиш билан боғлиқ барча низолар тарафлар ўртасида музокаралар ўтказиш йўли билан ҳал этилади. Тарафлар учун низоларни талабнома юбориш орқали кўриб чиқиш мажбурий ҳисобланади, шу билан бир қаторда талабномани кўриб чиқиш муддати – уни олгандан бошлаб 15 кунни ташкил қилади. Низолар бўйича келишувга эришилмаган тақдирда, низо суд идораларида кўриб чиқилади.",
            styles['NormalUz']
        ))

        self.story.append(KeepTogether(section9_elements))

        section10 = [
            "<b>10.1.</b> <b>Буюртмачи</b> футболнинг тўқнашувларга бой спорт туриш эканлиги хақида огоҳлантирилган ва машғулотлар пайтида, спорт мусобақалари, жароҳатлар ва шикастланишлар бўлиши мумкин, <b>Ижрочи</b> улар учун жавобгар эмас, агар уларнинг айблари сабабли бўлганлиги исботланмаган бўлса.",
            "<b>10.2.</b> <b>Ижрочи</b> спорт-машғулотидан ташқаридаги ҳар қандай тарбияланувчи билан боғлиқ оқибатларга жавоб бермайди.",
            "<b>10.3.</b> Тарафлардан бирининг ташаббуси билан ушбу шартнома ҳар қандай вақтда бир томонлама бекор қилиниши мумкин. Бунда, ўз мажбуриятларини бажармаган ёки лозим даражада бажармаган тараф 30 (ўттиз) календарь кун олдин бошқа тараф томонидан шартномани бекор қилиш тўғрисида огоҳлантирилиши талаб этилади. Шартнома у ёки бу сабаб билан бекор қилинганда ҳар ойлик абонемент тўлови қайтарилмайди.",
            "<b>10.4.</b> Шартнома имзоланган кундан бошлаб кучга киради ва шартнома бўйича мажбуриятлар тўлиқ бажарилгунга қадар амал қилади.",
            "<b>10.5.</b> Ҳеч қайси тараф ушбу шартнома бўйича ўз ҳуқуқ ва мажбуриятларини бошқа учинчи шахсга бошқа тарафнинг ёзма розилигисиз беришга ҳақли эмас.",
            "<b>10.6.</b> Ушбу Шартномада кўзда тутилмаган ўзаро муносабатлар Ўзбекистон Республикаси қонун Ҳужжатлари билан тартибга солинади.",
            "<b>10.7.</b> Шартномага киритилиши лозим бўлган барча ўзгартириш ва кўшимчалар фақат ёзма тартибда амалга оширилади ва Тарафлар имзолаб, муҳрлагандан сўнг асосий шартноманинг ажралмас қисми ҳисобланади.",
            "<b>10.8.</b> Мазкур шартнома иккита бир хил юридик кучга эга бўлган асл нусхаларда тузилади ва тарафлар томонидан имзолангандан бошлаб кучга киради."
        ]
        self._add_section("10", "Шартноманинг бошқа қоидалари", section10, is_list=True)

        self._add_spacer(4)

        # --- 11. Yuridik manzillar va imzolar ---
        self._add_signature_block()

        return self.story

    def add_attachments_to_pdf(self, base_pdf, pdf_urls, output_pdf):
        """
        Merge contract PDF with attachment PDFs, scaling all pages to A4 size.

        Uses lightweight PDF scaling (no image conversion) to reduce RAM usage.
        All pages are scaled/fitted to A4 dimensions while maintaining aspect ratio.
        """
        import os
        import httpx
        import tempfile
        from PyPDF2 import PdfReader, PdfWriter, Transformation
        from reportlab.lib.pagesizes import A4

        A4_WIDTH = A4[0]  # 595.27 points
        A4_HEIGHT = A4[1]  # 841.89 points

        valid_pdf_urls = [url for url in pdf_urls if url]
        if not valid_pdf_urls:
            print("[INFO] Birlashtirish uchun attachment yo'q")
            return None

        print(f"[INFO] {len(valid_pdf_urls)} ta PDF faylni birlashtirish (A4 razmeriga)...")

        # Download all PDFs synchronously
        def download_all_pdfs_sync():
            """Download all PDF files synchronously"""
            results = []
            for url in valid_pdf_urls:
                try:
                    if url.startswith(('http://', 'https://')):
                        # Download from S3
                        print(f"[DOWNLOAD] Yuklanmoqda: {url}")
                        with httpx.Client(timeout=30.0) as client:
                            response = client.get(url)
                            response.raise_for_status()
                            content = response.content

                        # Save to temp file
                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                            temp_pdf.write(content)
                            print(f"[OK] Yuklandi ({len(content)} bytes)")
                            results.append((temp_pdf.name, temp_pdf.name))
                    else:
                        # Local file
                        print(f"[FILE] Lokal fayl: {url}")
                        results.append((url, None))
                except Exception as e:
                    print(f"!!! PDF yuklab bo'lmadi: {type(e).__name__}: {e}")
                    results.append(None)
            return results

        results = download_all_pdfs_sync()

        # Create writer for final PDF
        writer = PdfWriter()

        # Add base PDF pages first when it exists
        if base_pdf and os.path.exists(base_pdf):
            try:
                with open(base_pdf, 'rb') as f:
                    reader = PdfReader(f)
                    for page in reader.pages:
                        writer.add_page(page)
                print(f"[OK] Asosiy shartnoma PDF qo'shildi ({len(reader.pages)} sahifa)")
            except Exception as e:
                print(f"!!! Asosiy PDF xato: {e}")
                raise

        temp_files_to_delete = []
        merged_count = 0
        total_pages = 0

        # Process each attachment PDF
        for result in results:
            if not result:
                continue

            pdf_path, temp_file = result
            if temp_file:
                temp_files_to_delete.append(temp_file)

            try:
                with open(pdf_path, 'rb') as f:
                    reader = PdfReader(f)
                    page_count = len(reader.pages)
                    print(f"[PAGE] [{merged_count + 1}] Qayta ishlanmoqda: {page_count} sahifa")

                    # Process each page
                    for page_num, page in enumerate(reader.pages):
                        try:
                            # Get current page dimensions
                            current_box = page.mediabox
                            current_width = float(current_box.width)
                            current_height = float(current_box.height)

                            # Calculate scale factor to fit in A4 while maintaining aspect ratio
                            scale_x = A4_WIDTH / current_width
                            scale_y = A4_HEIGHT / current_height
                            scale = min(scale_x, scale_y)  # Use smaller scale to fit entirely

                            # Calculate final dimensions after scaling
                            final_width = current_width * scale
                            final_height = current_height * scale

                            # Calculate centering offsets
                            offset_x = (A4_WIDTH - final_width) / 2
                            offset_y = (A4_HEIGHT - final_height) / 2

                            # Create transformation: scale then translate to center
                            transform = Transformation().scale(scale, scale).translate(offset_x, offset_y)

                            # Apply transformation
                            page.add_transformation(transform)

                            # Set page size to A4
                            page.mediabox.lower_left = (0, 0)
                            page.mediabox.upper_right = (A4_WIDTH, A4_HEIGHT)

                            # Add to writer
                            writer.add_page(page)
                            total_pages += 1
                            print(f"  [OK] Sahifa {page_num + 1}/{page_count} - A4 ga moslandi (scale: {scale:.2f})")

                        except Exception as page_error:
                            print(f"  !!! Sahifa {page_num + 1} xato: {type(page_error).__name__}: {page_error}")
                            continue

                merged_count += 1
                print(f"[OK] [{merged_count}] PDF to'liq qayta ishlandi")

            except Exception as e:
                print(f"!!! PDF ni qayta ishlashda xato: {type(e).__name__}: {e}")
                print(f"!!! Fayl: {pdf_path}")
                import traceback
                print(f"!!! Traceback: {traceback.format_exc()}")
                continue

        # Write final merged PDF
        with open(output_pdf, 'wb') as f:
            writer.write(f)

        print(f"[OK] Jami {merged_count} ta PDF ({total_pages} sahifa) birlashtirildi")
        print(f"[OK] Barcha sahifalar A4 razmeriga moslandi: {output_pdf}")

        # Cleanup temp files
        for f in temp_files_to_delete:
            try:
                os.unlink(f)
            except Exception:
                pass

        return output_pdf


    def generate(self, output_file):

        if not isinstance(output_file, (str, bytes, os.PathLike)):
            raise TypeError(f"output_file turi noto‘g‘ri: {type(output_file)}. Kutilgan: str yoki Path.")

        """PDF faylni yaratish"""
        try:
            image_urls = []
            data = self.data

            # Parse contract_images array
            contract_imgs_list = []
            contract_imgs = data.get("contract_images_urls")
            if contract_imgs:
                if isinstance(contract_imgs, str):
                    try:
                        parsed = json.loads(contract_imgs)
                        if isinstance(parsed, list):
                            contract_imgs_list = parsed
                        elif isinstance(parsed, str):
                            contract_imgs_list = [parsed]
                    except json.JSONDecodeError:
                        contract_imgs_list = [contract_imgs]
                elif isinstance(contract_imgs, list):
                    contract_imgs_list = contract_imgs

            # Build PDF in correct order:
            # 1. Form 086 (tibbiy forma)
            form_086 = data.get("form_086_url")
            if form_086:
                image_urls.append(form_086)

            # 2. Heart checkup (yurak tekshiruvi)
            heart_checkup = data.get("heart_checkup_url")
            if heart_checkup:
                image_urls.append(heart_checkup)

            # 3. Birth certificate front (tug'ilganlik guvohnomasi oldi)
            birth_cert = data.get("birth_certificate_url")
            if birth_cert:
                image_urls.append(birth_cert)

            # 4. Birth certificate back (optional) - contract_image_1 (index 0)
            if len(contract_imgs_list) > 0 and contract_imgs_list[0]:
                image_urls.append(contract_imgs_list[0])

            # 5. Father passport front (mandatory) - contract_image_2 (index 1)
            if len(contract_imgs_list) > 1 and contract_imgs_list[1]:
                image_urls.append(contract_imgs_list[1])

            # 6. Father passport back (optional) - contract_image_3 (index 2)
            if len(contract_imgs_list) > 2 and contract_imgs_list[2]:
                image_urls.append(contract_imgs_list[2])

            # 7. Mother passport front (mandatory) - contract_image_4 (index 3)
            if len(contract_imgs_list) > 3 and contract_imgs_list[3]:
                image_urls.append(contract_imgs_list[3])

            # 8. Mother passport back (optional) - contract_image_5 (index 4)
            if len(contract_imgs_list) > 4 and contract_imgs_list[4]:
                image_urls.append(contract_imgs_list[4])

            flowables = self.get_flowables()
            base_pdf_path = None

            if flowables:
                self.doc.filename = output_file
                self.doc.build(flowables)
                base_pdf_path = output_file
                print(f"[OK] Asosiy matnli PDF yaratildi: {output_file}")

            if image_urls:
                print(f"[INFO] {len(image_urls)} ta ilova fayl PDFga qo'shilmoqda...")
                merged_output = output_file if base_pdf_path is None else output_file.replace(".pdf", "_full.pdf")
                return self.add_attachments_to_pdf(base_pdf_path, image_urls, merged_output)

            if base_pdf_path:
                return base_pdf_path

            print("[INFO] Na matnli sahifa, na attachment yuborilgan. PDF generatsiya qilinmadi.")
            return None

        except Exception as e:
            print(f"!!! PDF yaratishda xato yuz berdi: {e}")
            return None


def main():
    """Asosiy funksiya"""
    data_file = "shartnoma_data.json"
    output_file = "FK_Bunyodkor_Shartnoma.pdf"

    print("=" * 60)
    print("FK BUNYODKOR ШАРТНОМА ГЕНЕРАТОР (PLATYPUS)")
    print("=" * 60)

    # PDF yaratish uchun ma'lumotlarni yuklash va generatsiya
    try:
        generator = ContractPDFGenerator(data_file)
        generator.generate(output_file)
    except SystemExit:
        # JSON fayl topilmaganda va namuna yaratilganda dastur tugatilishi
        print(f"!!! Iltimos, '{data_file}' faylini to'ldirib, qayta ishga tushiring.")
    except Exception as e:
        print(f"!!! Noma'lum xato yuz berdi: {e}")


if __name__ == "__main__":
    main()
