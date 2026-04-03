from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import selectinload
from datetime import datetime
import hashlib
from pydantic import BaseModel
import re
import secrets

from app.core.db import get_db
from app.core.config import settings
from app.models.domain import Contract, Student
from app.models.finance import Transaction
from app.models.enums import PaymentSource, PaymentStatus, ContractStatus
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/click", tags=["Click Payment"])
security = HTTPBasic()


class ClickRequest(BaseModel):
    """
    Click callback protokoli uchun to'liq request model.
    Click dan kelgan barcha zarur fieldlar qo'shilgan.
    """
    action: int
    service_id: int

    # MUHIM: Click callback protokolida bu fieldlar bo'lishi kerak
    click_trans_id: int | None = None  # Click tizimidagi tranzaksiya ID
    click_paydoc_id: int | None = None  # Click payment document ID

    merchant_trans_id: str | None = None  # Bizning tizimimizdagi tranzaksiya ID
    merchant_prepare_id: int | None = None  # Prepare qilingan tranzaksiya ID
    merchant_confirm_id: int | None = None  # Confirm qilingan tranzaksiya ID
    attempt_trans_id: int | None = None  # ← SHUNI QO‘SH

    amount: str | float | None = None  # To'lov summasi (top-level yoki params ichida)
    sign_time: str | None = None
    sign_string: str | None = None

    params: dict | None = None
    from_date: str | None = None
    till_date: str | None = None


def verify_basic_auth(credentials: HTTPBasicCredentials) -> bool:
    """Basic Authentication tekshiruvi"""
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"),
        settings.CLICK_AUTH_USERNAME.encode("utf8")
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        settings.CLICK_AUTH_PASSWORD.encode("utf8")
    )
    return correct_username and correct_password


def normalize_identifier(identifier: str) -> str:
    """
    Shartnoma raqamini normalizatsiya qilish.
    Kirill harflarni lotin ekvivalentiga o'zgartiradi.
    """
    cyrillic_to_latin = {
        'А': 'A', 'а': 'a',
        'В': 'B', 'в': 'b',
        'С': 'C', 'с': 'c',
        'Е': 'E', 'е': 'e',
        'К': 'K', 'к': 'k',
        'М': 'M', 'м': 'm',
        'Н': 'H', 'н': 'h',
        'О': 'O', 'о': 'o',
        'Р': 'P', 'р': 'p',
        'Т': 'T', 'т': 't',
        'Х': 'X', 'х': 'x',
    }

    normalized = ''.join(cyrillic_to_latin.get(char, char) for char in identifier)
    normalized = normalized.upper()
    normalized = re.sub(r'[^A-Z0-9-]', '', normalized)

    return normalized


def cyrillic_to_latin(text: str) -> str:
    """To'liq kirill-lotin transliteratsiyasi"""
    if not text:
        return text

    cyrillic_map = {
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'J', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'X', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch', 'Ъ': "'",
        'Ы': 'I', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
        'Ғ': 'G\'', 'Қ': 'Q', 'Ў': 'O\'', 'Ҳ': 'H',
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'j', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'x', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': "'",
        'ы': 'i', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'ғ': 'g\'', 'қ': 'q', 'ў': 'o\'', 'ҳ': 'h'
    }

    result = ''
    for char in text:
        result += cyrillic_map.get(char, char)
    return result


def is_cyrillic(text: str) -> bool:
    """Matnda kirill harflari borligini tekshirish"""
    if not text:
        return False
    return bool(re.search('[а-яА-ЯёЁўҮғҒқҚҳҲ]', text))


def translate_full_name(text: str) -> dict:
    """To'liq ismni 3 tilda qaytarish"""
    if not text:
        return {
            "FISH": "",
            "ФИО": "",
            "Full name": ""
        }

    text = text.strip()

    if is_cyrillic(text):
        latin_version = cyrillic_to_latin(text)
        return {
            "FISH": latin_version,
            "ФИО": text,
            "Full name": latin_version
        }
    else:
        return {
            "FISH": text,
            "ФИО": text,
            "Full name": text
        }


def translate_address(text: str) -> dict:
    """Manzilni 3 tilda qaytarish"""
    if not text:
        return {
            "Manzil": "",
            "Адрес": "",
            "Address": ""
        }

    text = text.strip()

    if is_cyrillic(text):
        latin_version = cyrillic_to_latin(text)
        return {
            "Manzil": latin_version,
            "Адрес": text,
            "Address": latin_version
        }
    else:
        return {
            "Manzil": text,
            "Адрес": text,
            "Address": text
        }


def translate_contract_status(status: str) -> dict:
    """Shartnoma holatini 3 tilda qaytarish"""
    translations = {
        "active": {
            "Shartnoma holati": "Faol",
            "Состояние договора": "Активный",
            "Contract status": "Active"
        },
        "inactive": {
            "Shartnoma holati": "Faol emas",
            "Состояние договора": "Неактивный",
            "Contract status": "Inactive"
        },
        "completed": {
            "Shartnoma holati": "Yakunlangan",
            "Состояние договора": "Завершенный",
            "Contract status": "Completed"
        },
        "cancelled": {
            "Shartnoma holati": "Bekor qilingan",
            "Состояние договора": "Отменен",
            "Contract status": "Cancelled"
        }
    }
    return translations.get(status.lower(), {
        "Shartnoma holati": status,
        "Состояние договора": status,
        "Contract status": status
    })


def debug_click_signature(data: ClickRequest, raw_string: str, calculated: str):
    print("\n" + "="*60)
    print("🧾 CLICK SIGNATURE DEBUG")
    print("="*60)

    print("→ Incoming fields:")
    print(f"  click_trans_id     : {repr(data.click_trans_id)}")
    print(f"  service_id         : {repr(data.service_id)}")
    print(f"  merchant_trans_id  : {repr(data.merchant_trans_id)}")
    print(f"  merchant_prepare_id: {repr(data.merchant_prepare_id)}")
    print(f"  amount             : {repr(data.amount)}")
    print(f"  action             : {repr(data.action)}")
    print(f"  sign_time          : {repr(data.sign_time)}")
    print(f"  sign_string(in)    : {repr(data.sign_string)}")

    print("\n→ Used for hash:")
    print(f"  RAW STRING         : {raw_string}")

    print("\n→ Hash compare:")
    print(f"  CALCULATED         : {calculated}")
    print(f"  INCOMING           : {data.sign_string}")
    print(f"  MATCH              : {calculated == data.sign_string}")

    print("="*60 + "\n")





import hashlib

def build_params_iv(raw_payload: dict) -> str:
    params = raw_payload.get("params", {})
    iv = ""
    for key in params:      # aynan payload'dagi tartib
        iv += str(params[key])
    return iv

import hashlib

def verify_signature(data: ClickRequest, payload: dict) -> bool:
    secret_key = settings.CLICK_SECRET_KEY

    click_paydoc_id = str(payload.get("click_paydoc_id", ""))
    attempt_trans_id = str(payload.get("attempt_trans_id", ""))
    service_id = str(payload.get("service_id", ""))
    action = str(payload.get("action", ""))
    sign_time = str(payload.get("sign_time", "")).strip()

    params_iv = build_params_iv(payload)

    raw = (
        click_paydoc_id +
        attempt_trans_id +
        service_id +
        secret_key +
        params_iv +
        action +
        sign_time
    )

    calculated = hashlib.md5(raw.encode()).hexdigest()

    print("RAW:", raw)
    print("CALC:", calculated)
    print("IN:", payload.get("sign_string"))

    return calculated == payload.get("sign_string")




from starlette.datastructures import FormData

from  fastapi import  Request, Response

@router.post("/payment")
async def click_payment(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
):

    if not verify_basic_auth(credentials):
        raise HTTPException(status_code=401, detail="Auth failed")

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        payload = await request.json()
    else:
        form: FormData = await request.form()
        payload = {}
        for key, value in form.items():
            # params[contract] -> params.contract
            if "[" in key and "]" in key:
                root, child = key.replace("]", "").split("[")
                payload.setdefault(root, {})[child] = value
            else:
                payload[key] = value

    print("RAW PAYLOAD:", payload)

    data = ClickRequest(**payload)

    if not data.click_trans_id:
        data.click_trans_id = payload.get("attempt_trans_id")

    if not data.merchant_trans_id:
        data.merchant_trans_id = (data.params or {}).get("contract")

    if not data.amount:
        data.amount = (data.params or {}).get("amount")

    action = data.action

    # Service ID tekshiruvi
    if str(data.service_id) != settings.CLICK_SERVICE_ID:
        return {
            "error": -3,
            "error_note": {
                "uz": "Xizmat topilmadi",
                "ru": "Сервис не найден",
                "en": "Service not found"
            }
        }

    # ==================== ACTION 0: CHECK ====================
    if action == 0:
        """
        Shartnoma mavjudligini va to'lovga tayyor ekanligini tekshirish.
        Bu action signature tekshiruvini talab qilmaydi.
        """
        if not data.params or "contract" not in data.params:
            return {
                "error": -8,
                "error_note": {
                    "uz": "CLICK dan so'rovda xatolik",
                    "ru": "Ошибка в запросе от CLICK",
                    "en": "Error in request from CLICK"
                }
            }

        # Shartnoma raqamini normalizatsiya qilish
        raw_contract = data.params.get("contract") or ""
        contract_number = normalize_identifier(raw_contract)

        print(f"🔍 SEARCHING CONTRACT >>> {repr(contract_number)}")

        # Shartnomani bazadan qidirish
        stmt = (
            select(Contract)
            .options(selectinload(Contract.student))
            .where(Contract.contract_number == contract_number)
            .limit(1)
        )

        result = await db.execute(stmt)
        contract = result.scalar()

        print(f"✅ FOUND CONTRACT >>> {contract}")

        if not contract:
            return {
                "error": -5,
                "error_note": "Shartnoma topilmadi"

            }

        if contract.status != ContractStatus.ACTIVE:
            return {
                "error": -5,
                "error_note": "Shartnoma faol emas. To'lov faqat faol shartnomalar bo'yicha mumkin"
            }

        student = contract.student

        if not student:
            return {
                "error": -5,
                "error_note": "Talaba topilmadi"

            }

        # Talaba ma'lumotlarini tayyorlash
        first_name = student.first_name or ""
        last_name = student.last_name or ""
        full_name = f"{first_name} {last_name}".strip()

        if not full_name:
            full_name = "Unknown"

        # Muvaffaqiyatli javob qaytarish
        return {
            "error": 0,
            "error_note": "Success",
            "params": {
                "contract": contract.contract_number,
                "full_name": full_name,
                "phone": student.phone,
                "address": student.address,
                "monthly_fee": float(contract.monthly_fee),
                "contract_status": contract.status.value,
                "start_date": contract.start_date.isoformat(),
                "end_date": contract.end_date.isoformat()
            }
        }

    # ==================== ACTION 1: PREPARE ====================
    elif action == 1:
        """
        To'lovni tayyorlash (prepare) stage.
        Bu yerda:
        1. Signature tekshiriladi
        2. Shartnoma va summa validatsiyasi
        3. Dublikat to'lov tekshiruvi
        4. PENDING status bilan tranzaksiya yaratiladi
        """

        # ✅ SIGNATURE TEKSHIRUVI
        if not verify_signature(data, payload):


            return {
                "error": -1,
                "error_note": {
                    "uz": "IMZO TEKSHIRUVI MUVAFFAQIYATSIZ!",
                    "ru": "SIGN CHECK FAILED!",
                    "en": "SIGN CHECK FAILED!"
                }
            }

        if not data.params or "contract" not in data.params:
            return {
                "error": -8,
                "error_note": {
                    "uz": "CLICK dan so'rovda xatolik",
                    "ru": "Ошибка в запросе от CLICK",
                    "en": "Error in request from CLICK"
                }
            }

        # Shartnoma raqamini normalizatsiya qilish
        raw_contract = data.params.get("contract") or ""
        contract_number = normalize_identifier(raw_contract)

        # To'lov summasini olish
        try:
            # amount top-level yoki params ichida bo'lishi mumkin
            amount = data.amount if data.amount is not None else data.params.get("amount")
            amount = float(amount)
        except (TypeError, ValueError):
            return {
                "error": -2,
                "error_note":"Noto'g'ri summa"

            }

        # Shartnomani bazadan qidirish
        contract_result = await db.execute(
            select(Contract)
            .options(selectinload(Contract.student))
            .where(Contract.contract_number == contract_number)
        )
        contract = contract_result.scalar_one_or_none()

        if not contract:
            return {
                "error": -5,
                "error_note":"Shartnoma topilmadi"

            }

        if contract.status != ContractStatus.ACTIVE:
            return {
                "error": -5,
                "error_note": "Shartnoma faol emas"


            }
        from decimal import Decimal
        # To'lov summasini tekshirish
        paid = Decimal(str(amount))
        expected = Decimal(str(contract.monthly_fee))

        if paid < expected:
            return {
                "error": -2,
                "error_note":f"To'lov yetarli emas. Kamida {expected} so'm bo'lishi kerak"

            }

        # ✅ TO'G'RILANGAN: payment_month va payment_year ni to'g'ri olish
        # ESLATMA: Sizda params da almashgan edi (month=2026, year=1)
        payment_month_raw = data.params.get("payment_month")
        payment_year_raw = data.params.get("payment_year")

        try:
            payment_month = int(payment_month_raw)
            payment_year = int(payment_year_raw)
        except (TypeError, ValueError):
            return {
                "error": -8,
                "error_note":"Yil yoki Oy noto‘g‘ri"
            }

        # Agar almashgan bo‘lsa tuzatamiz
        if 1 <= payment_year <= 12 and payment_month > 12:
            payment_year, payment_month = payment_month, payment_year
            print("⚠️ WARNING: payment_month va payment_year almashgan edi, tuzatildi!")

        # Final validatsiya
        if not (1 <= payment_month <= 12):
            return {
                "error": -8,
                "error_note": "payment_month 1-12 oralig‘ida bo‘lishi kerak"

            }

        # Shartnoma muddatini tekshirish
        from datetime import date as date_class
        payment_date = date_class(payment_year, payment_month, 1)
        contract_start_month = date_class(contract.start_date.year, contract.start_date.month, 1)
        contract_end_month = date_class(contract.end_date.year, contract.end_date.month, 1)

        if payment_date < contract_start_month:
            return {
                "error": -5,
                "error_note": f"Shartnoma hali boshlanmagan. Boshlanishi: {contract.start_date.isoformat()}"

            }

        if payment_date > contract_end_month:
            return {
                "error": -5,
                "error_note":f"Shartnoma muddati tugagan. Tugash: {contract.end_date.isoformat()}"
            }

        # Dublikat to'lovni tekshirish
        duplicate_check = await db.execute(
            select(Transaction).where(
                Transaction.contract_id == contract.id,
                Transaction.status == PaymentStatus.SUCCESS,
                Transaction.payment_year == payment_year,
                cast(Transaction.payment_months, JSONB).op('@>')(cast([payment_month], JSONB))
            )
        )
        duplicate = duplicate_check.scalar_one_or_none()

        if duplicate:
            month_names_ru = {
                1: "январь", 2: "февраль", 3: "март", 4: "апрель",
                5: "май", 6: "июнь", 7: "июль", 8: "август",
                9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
            }
            month_names_uz = {
                1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel",
                5: "may", 6: "iyun", 7: "iyul", 8: "avgust",
                9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr"
            }
            month_names_en = {
                1: "January", 2: "February", 3: "March", 4: "April",
                5: "May", 6: "June", 7: "July", 8: "August",
                9: "September", 10: "October", 11: "November", 12: "December"
            }
            return {
                "error": -4,
                "error_note":  f"{month_names_uz[payment_month]} {payment_year} uchun to'lov allaqachon mavjud"


            }

        # Mavjud tranzaksiyani tekshirish (click_trans_id yoki click_paydoc_id orqali)
        existing_result = await db.execute(
            select(Transaction).where(
                Transaction.external_id == str(data.click_trans_id or data.click_paydoc_id)
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            if existing.status == PaymentStatus.SUCCESS:
                return {
                    "error": -4,
                    "error_note": "Allaqachon to'langan"

                }
            if existing.status == PaymentStatus.CANCELLED:
                return {
                    "error": -9,
                    "error_note": "Tranzaksiya bekor qilingan"

                }
            # Agar PENDING bo'lsa, mavjud tranzaksiyani qaytaramiz
            return {
                "click_trans_id": data.click_trans_id,
                "click_paydoc_id": data.click_paydoc_id,
                "merchant_prepare_id": existing.id,
                "error": 0,
                "error_note": "Success",
                "params": {}
            }
        clean_amount = float(contract.monthly_fee)

        # Yangi tranzaksiya yaratish
        transaction = Transaction(
            external_id=str(data.click_trans_id or data.click_paydoc_id),
            amount=clean_amount,
            source=PaymentSource.CLICK,
            status=PaymentStatus.PENDING,
            contract_id=contract.id,
            student_id=contract.student_id,
            payment_year=payment_year,
            payment_months=[payment_month],
            comment=f"Click prepare: click_trans_id={data.click_trans_id}, month={payment_month}/{payment_year}"
        )

        db.add(transaction)
        await db.commit()
        await db.refresh(transaction)

        print(f"✅ Transaction created: ID={transaction.id}, month={payment_month}/{payment_year}")

        return {
            "click_trans_id": data.click_trans_id,
            "click_paydoc_id": data.click_paydoc_id,
            "merchant_prepare_id": transaction.id,
            "error": 0,
            "error_note": "Success",
            "params": {}
        }

    # ==================== ACTION 2: COMPLETE ====================
    elif action == 2:
        """
        To'lovni tasdiqlash (complete) stage.
        Bu yerda:
        1. Signature tekshiriladi
        2. Prepare qilingan tranzaksiya topiladi
        3. Final validatsiyalar
        4. Status SUCCESS ga o'zgartiriladi
        """

        # ✅ SIGNATURE TEKSHIRUVI
        if not verify_signature(data, payload):

            return {
                "error": -1,
                "error_note": {
                    "uz": "IMZO TEKSHIRUVI MUVAFFAQIYATSIZ!",
                    "ru": "SIGN CHECK FAILED!",
                    "en": "SIGN CHECK FAILED!"
                }
            }

        merchant_prepare_id = data.merchant_prepare_id

        if not merchant_prepare_id:
            return {
                "error": -8,
                "error_note": {
                    "uz": "CLICK dan so'rovda xatolik (merchant_prepare_id yo'q)",
                    "ru": "Ошибка в запросе от CLICK (нет merchant_prepare_id)",
                    "en": "Error in request from CLICK (no merchant_prepare_id)"
                }
            }

        # Tranzaksiyani topish
        transaction_result = await db.execute(
            select(Transaction).where(Transaction.id == merchant_prepare_id)
        )
        transaction = transaction_result.scalar_one_or_none()

        if not transaction:
            return {
                "error": -6,
                "error_note": {
                    "uz": "Tranzaksiya topilmadi",
                    "ru": "Транзакция не найдена",
                    "en": "Transaction not found"
                }
            }

        # click_trans_id yoki click_paydoc_id ni tekshirish
        expected_external_id = str(data.click_trans_id or data.click_paydoc_id)
        if transaction.external_id != expected_external_id:
            return {
                "error": -6,
                "error_note": {
                    "uz": "Tranzaksiya ID mos kelmadi",
                    "ru": "ID транзакции не совпадает",
                    "en": "Transaction ID mismatch"
                }
            }

        # Agar allaqachon SUCCESS bo'lsa
        if transaction.status == PaymentStatus.SUCCESS:
            return {
                "click_trans_id": data.click_trans_id,
                "click_paydoc_id": data.click_paydoc_id,
                "merchant_confirm_id": transaction.id,
                "error": -4,
                "error_note": "Allaqachon to'langan"


            }

        # Agar CANCELLED bo'lsa
        if transaction.status == PaymentStatus.CANCELLED:
            return {
                "error": -9,
                "error_note": {
                    "uz": "Tranzaksiya bekor qilingan",
                    "ru": "Транзакция отменена",
                    "en": "Transaction cancelled"
                }
            }

        # Shartnomani tekshirish
        contract_result = await db.execute(
            select(Contract).where(Contract.id == transaction.contract_id)
        )
        contract = contract_result.scalar_one_or_none()

        if not contract:
            return {
                "error": -6,
                "error_note": "Shartnoma topilmadi"

            }

        if contract.status != ContractStatus.ACTIVE:
            return {
                "error": -5,
                "error_note": "Shartnoma faol emas"


            }

        # To'lov sanasini tekshirish
        payment_year = transaction.payment_year
        payment_month = transaction.payment_months[0] if transaction.payment_months else datetime.now().month

        from datetime import date as date_class
        payment_date = date_class(payment_year, payment_month, 1)
        contract_start_month = date_class(contract.start_date.year, contract.start_date.month, 1)
        contract_end_month = date_class(contract.end_date.year, contract.end_date.month, 1)

        if payment_date < contract_start_month or payment_date > contract_end_month:
            return {
                "error": -5,
                "error_note": "Shartnoma muddati tugagan yoki hali boshlanmagan"


            }

        # Final dublikat tekshiruvi (race condition oldini olish)
        final_duplicate_check = await db.execute(
            select(Transaction).where(
                Transaction.contract_id == contract.id,
                Transaction.status == PaymentStatus.SUCCESS,
                Transaction.payment_year == payment_year,
                cast(Transaction.payment_months, JSONB).op('@>')(cast([payment_month], JSONB)),
                Transaction.id != transaction.id
            )
        )
        final_duplicate = final_duplicate_check.scalar_one_or_none()

        if final_duplicate:
            # Agar boshqa tranzaksiya SUCCESS bo'lgan bo'lsa, bu tranzaksiyani CANCEL qilamiz
            transaction.status = PaymentStatus.CANCELLED
            transaction.comment = f"Cancelled: duplicate payment for month {payment_month}/{payment_year}"
            await db.commit()
            return {
                "error": -4,
                "error_note":"Ushbu oy uchun to'lov allaqachon mavjud"

            }

        # Tranzaksiyani SUCCESS ga o'zgartirish
        transaction.status = PaymentStatus.SUCCESS
        transaction.paid_at = datetime.utcnow()
        transaction.comment = f"Click confirmed: click_trans_id={data.click_trans_id}, month={payment_month}/{payment_year}"

        await db.commit()
        await db.refresh(transaction)

        print(f"✅ Payment completed: Transaction ID={transaction.id}, month={payment_month}/{payment_year}")

        return {
            "click_trans_id": data.click_trans_id,
            "click_paydoc_id": data.click_paydoc_id,
            "merchant_confirm_id": transaction.id,
            "error": 0,
            "error_note": "Success",
            "params": {}
        }

    else:
        # Noma'lum action
        return {
            "error": -3,
            "error_note": {
                "uz": "Harakat topilmadi",
                "ru": "Действие не найдено",
                "en": "Action not found"
            }
        }