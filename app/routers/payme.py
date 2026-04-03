from typing import Annotated
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import selectinload
from datetime import datetime
import base64
from sqlalchemy import String
import re
from app.core.db import get_db
from app.core.config import settings
from app.models.domain import Contract, Student
from app.models.finance import Transaction
from app.models.enums import PaymentSource, PaymentStatus, ContractStatus

router = APIRouter(prefix="/payme", tags=["Payme Payment"])

# Global o'zgaruvchi - parolni vaqtinchalik saqlash uchun
CURRENT_PAYME_PASSWORD = None


class PaymeError:
    INVALID_AMOUNT = -31001
    INVALID_ACCOUNT = -31050
    COULD_NOT_PERFORM = -31008
    TRANSACTION_NOT_FOUND = -31003
    INVALID_AUTHORIZATION = -32504
    METHOD_NOT_FOUND = -32601
    PARSE_ERROR = -32700
    INVALID_PARAMS = -32602


def check_authorization(request: Request) -> bool:
    global CURRENT_PAYME_PASSWORD

    auth_header = request.headers.get("Authorization", "")
    x_auth = request.headers.get("X-Auth", "")

    # print(f"🔑 Authorization header: {auth_header}")
    # print(f"🔑 X-Auth header: {x_auth}")
    # print(f"📋 All headers: {dict(request.headers)}")

    # Joriy aktiv parolni aniqlash
    active_password = CURRENT_PAYME_PASSWORD if CURRENT_PAYME_PASSWORD else settings.PAYME_KEY
    # print(f"🔐 Active password: {active_password}")

    if x_auth:
        result = x_auth == active_password
        # print(f"✅ X-Auth check result: {result}")
        return result

    if not auth_header:
        # print("❌ No auth headers found")
        return False

    if not auth_header.startswith("Basic "):
        # print("❌ Auth header doesn't start with 'Basic '")
        return False

    try:
        encoded = auth_header.replace("Basic ", "")
        decoded = base64.b64decode(encoded).decode("utf-8")

        # print(f"🔓 Decoded: {decoded}")

        if ":" not in decoded:
            # print("❌ No colon in decoded string")
            return False

        login, password = decoded.split(":", 1)
        #
        # print(f"👤 Login: {login}")
        # print(f"🔒 Password: {password}")

        result = login == "Paycom" and password == active_password
        # print(f"✅ Basic Auth result: {result}")

        return result

    except Exception as e:
        print(f"❌ Exception: {e}")
        return False


def create_error_response(error_code: int, message: str, request_id: int = None):
    response = {
        "error": {
            "code": error_code,
            "message": message
        }
    }
    if request_id is not None:
        response["id"] = request_id
    return response


def create_success_response(result: dict, request_id: int):
    return {
        "result": result,
        "id": request_id
    }


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

@router.post("/payment")
async def payme_payment(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db)]
):
    try:
        body = await request.json()
    except Exception:
        return create_error_response(
            PaymeError.PARSE_ERROR,
            "Ошибка разбора JSON"
        )

    method = body.get("method")
    params = body.get("params", {})
    request_id = body.get("id")

    if not method:
        return create_error_response(
            PaymeError.METHOD_NOT_FOUND,
            "Метод не найден",
            request_id
        )

    # ChangePassword uchun alohida tartib
    if method == "ChangePassword":
        return await change_password(params, request_id, request)

    # Qolgan metodlar uchun autorizatsiya
    if not check_authorization(request):
        return create_error_response(
            PaymeError.INVALID_AUTHORIZATION,
            "Недостаточно привилегий для выполнения метода",
            request_id
        )

    if method == "CheckPerformTransaction":
        return await check_perform_transaction(params, request_id, db)

    elif method == "CreateTransaction":
        return await create_transaction(params, request_id, db)

    elif method == "PerformTransaction":
        return await perform_transaction(params, request_id, db)

    elif method == "CheckTransaction":
        return await check_transaction(params, request_id, db)

    elif method == "CancelTransaction":
        return await cancel_transaction(params, request_id, db)
    elif method == "GetStatement":  # ✅ YANGI METOD
        return await get_statement(params, request_id, db)

    else:
        return create_error_response(
            PaymeError.METHOD_NOT_FOUND,
            "Метод не найден",
            request_id
        )


async def change_password(params: dict, request_id: int, request: Request):
    global CURRENT_PAYME_PASSWORD

    new_password = params.get("password")

    if not new_password:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Новый пароль не указан",
                    "uz": "Yangi parol ko'rsatilmagan",
                    "en": "New password not provided"
                }
            },
            "id": request_id
        }

    if not check_authorization(request):
        return {
            "error": {
                "code": PaymeError.INVALID_AUTHORIZATION,
                "message": {
                    "ru": "Недостаточно привилегий для выполнения метода",
                    "uz": "Usulni bajarish uchun huquqlar yetarli emas",
                    "en": "Insufficient privileges to execute method"
                }
            },
            "id": request_id
        }

    old_password = CURRENT_PAYME_PASSWORD if CURRENT_PAYME_PASSWORD else settings.PAYME_KEY
    CURRENT_PAYME_PASSWORD = new_password


    return create_success_response({"success": True}, request_id)


async def check_perform_transaction(params: dict, request_id: int, db: AsyncSession):
    """
    2 bosqichli tekshiruv:
    1. Faqat contract → student ma'lumotlarini ko'rsatish
    2. Contract + amount + year + month → to'lovni tasdiqlash
    """
    amount = params.get("amount")
    account = params.get("account", {})

    if not account:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Неверные параметры",
                    "uz": "Noto'g'ri parametrlar",
                    "en": "Invalid parameters"
                }
            },
            "id": request_id
        }

    contract_number = account.get("contract")

    if not contract_number:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Номер договора не указан",
                    "uz": "Shartnoma raqami ko'rsatilmagan",
                    "en": "Contract number not provided"
                }
            },
            "id": request_id
        }
    normalized_contract_number = normalize_identifier(contract_number)

    # Contract va Student ni olish
    contract_result = await db.execute(
        select(Contract)
        .options(selectinload(Contract.student))
        .where(Contract.contract_number == normalized_contract_number)
    )
    contract = contract_result.scalar_one_or_none()

    if not contract:
        return {
            "error": {
                "code": PaymeError.INVALID_ACCOUNT,
                "message": {
                    "ru": "Договор не найден",
                    "uz": "Shartnoma topilmadi",
                    "en": "Contract not found"
                },
                "data": "account.contract"
            },
            "id": request_id
        }

    if contract.status != ContractStatus.ACTIVE:
        return {
            "error": {
                "code": PaymeError.INVALID_ACCOUNT,
                "message": {
                    "ru": "Договор не активен. Оплата возможна только по активным договорам",
                    "uz": "Shartnoma faol emas. To'lov faqat faol shartnomalar bo'yicha mumkin",
                    "en": "Contract is not active. Payment is only possible for active contracts"
                },
                "data": "account.contract"
            },
            "id": request_id
        }

    student = contract.student

    # ✅ BOSQICH 1: Faqat contract (student ma'lumotlarini ko'rish)
    if not amount:
        print("📋 Step 1: Showing student info only")
        return create_success_response(
            {
                "allow": True,
                "additional": {
                    "name": f"{student.first_name} {student.last_name}",
                    "phone": student.phone or "",
                    "contract_status": contract.status.value,
                    "contract_number": contract.contract_number,
                    "monthly_fee": float(contract.monthly_fee),
                    "start_date": contract.start_date.isoformat(),
                    "end_date": contract.end_date.isoformat()
                }
            },
            request_id
        )

    # ✅ BOSQICH 2: To'liq ma'lumot (to'lovni tasdiqlash)
    # print("💰 Step 2: Full payment validation")

    amount_sum = float(amount) / 100
    expected_amount = float(contract.monthly_fee)

    if amount_sum < expected_amount:
        return {
            "error": {
                "code": PaymeError.INVALID_AMOUNT,
                "message": {
                    "ru": f"Сумма должна быть не меньше {expected_amount}",
                    "uz": f"Summa kamida {expected_amount} bo'lishi kerak",
                    "en": f"Amount must be at least {expected_amount}"
                }
            },
            "id": request_id
        }

    payment_year = account.get("payment_year")
    payment_month = account.get("payment_month")

    if payment_year is not None:
        try:
            payment_year = int(payment_year)
        except (TypeError, ValueError):
            return {
                "error": {
                    "code": PaymeError.INVALID_PARAMS,
                    "message": {
                        "ru": "Неверный год оплаты",
                        "uz": "Noto'g'ri to'lov yili",
                        "en": "Invalid payment year"
                    }
                },
                "id": request_id
            }
    else:
        payment_year = datetime.now().year

    if payment_month is not None:
        try:
            payment_month = int(payment_month)
        except (TypeError, ValueError):
            return {
                "error": {
                    "code": PaymeError.INVALID_PARAMS,
                    "message": {
                        "ru": "Неверный месяц оплаты",
                        "uz": "Noto'g'ri to'lov oyi",
                        "en": "Invalid payment month"
                    }
                },
                "id": request_id
            }
    else:
        payment_month = datetime.now().month

    if not (1 <= payment_month <= 12):
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Неверный месяц оплаты",
                    "uz": "Noto'g'ri to'lov oyi",
                    "en": "Invalid payment month"
                }
            },
            "id": request_id
        }

    from datetime import date as date_class
    payment_date = date_class(payment_year, payment_month, 1)
    contract_start_month = date_class(contract.start_date.year, contract.start_date.month, 1)
    contract_end_month = date_class(contract.end_date.year, contract.end_date.month, 1)

    if payment_date < contract_start_month:
        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": f"Договор еще не начался. Начало: {contract.start_date.isoformat()}",
                    "uz": f"Shartnoma hali boshlanmagan. Boshlanishi: {contract.start_date.isoformat()}",
                    "en": f"Contract has not started yet. Start date: {contract.start_date.isoformat()}"
                }
            },
            "id": request_id
        }

    if payment_date > contract_end_month:
        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": f"Договор истек. Окончание: {contract.end_date.isoformat()}",
                    "uz": f"Shartnoma muddati tugagan. Tugash sanasi: {contract.end_date.isoformat()}",
                    "en": f"Contract has expired. End date: {contract.end_date.isoformat()}"
                }
            },
            "id": request_id
        }

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
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": f"Оплата за {month_names_ru[payment_month]} {payment_year} уже существует",
                    "uz": f"{month_names_uz[payment_month]} {payment_year} uchun to'lov allaqachon mavjud",
                    "en": f"Payment for {month_names_en[payment_month]} {payment_year} already exists"
                }
            },
            "id": request_id
        }

    # To'liq validatsiya o'tdi
    return create_success_response(
        {
            "allow": True,
            "additional": {
                "name": f"{student.first_name} {student.last_name}",
                "contract_status": contract.status.value,
                "contract_number": contract.contract_number,
                "monthly_fee": float(contract.monthly_fee)
            }
        },
        request_id
    )


async def create_transaction(params: dict, request_id: int, db: AsyncSession):
    payme_id = params.get("id")
    time = params.get("time")
    amount = params.get("amount")
    account = params.get("account", {})

    if not all([payme_id, time, amount, account]):
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Неверные параметры",
                    "uz": "Noto'g'ri parametrlar",
                    "en": "Invalid parameters"
                }
            },
            "id": request_id
        }

    contract_number = account.get("contract")
    if not contract_number:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Номер договора не указан",
                    "uz": "Shartnoma raqami ko'rsatilmagan",
                    "en": "Contract number not provided"
                }
            },
            "id": request_id
        }

    print(f"🔍 CreateTransaction: payme_id={payme_id}, contract={contract_number}")
    normalized_contract_number = normalize_identifier(contract_number)

    # ✅ Mavjud tranzaksiyani tekshirish
    existing_result = await db.execute(
        select(Transaction).where(
            Transaction.external_id == str(payme_id)
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        print(f"✅ Transaction already exists: id={existing.id}, status={existing.status}")

        if existing.status == PaymentStatus.SUCCESS:
            return create_success_response(
                {
                    "create_time": int(existing.created_at.timestamp() * 1000),
                    "perform_time": int(existing.paid_at.timestamp() * 1000) if existing.paid_at else 0,
                    "cancel_time": 0,
                    "transaction": str(existing.id),
                    "state": 2,
                    "reason": None
                },
                request_id
            )

        if existing.status == PaymentStatus.CANCELLED:
            # ✅ cancelled_at dan olish
            cancel_time = int(existing.cancelled_at.timestamp() * 1000) if existing.cancelled_at else 0

            # State aniqlash
            state = -2 if existing.paid_at else -1

            # Reason
            reason = 5
            if existing.comment and "reason" in existing.comment.lower():
                try:
                    reason = int(existing.comment.split("reason")[-1].strip())
                except:
                    reason = 5

            return create_success_response(
                {
                    "create_time": int(existing.created_at.timestamp() * 1000),
                    "perform_time": int(existing.paid_at.timestamp() * 1000) if existing.paid_at else 0,
                    "cancel_time": cancel_time,
                    "transaction": str(existing.id),
                    "state": state,
                    "reason": reason
                },
                request_id
            )

        # PENDING
        return create_success_response(
            {
                "create_time": int(existing.created_at.timestamp() * 1000),
                "perform_time": 0,
                "cancel_time": 0,
                "transaction": str(existing.id),
                "state": 1,
                "reason": None
            },
            request_id
        )

    # ✅ Contract ni topish
    contract_result = await db.execute(
        select(Contract)
        .options(selectinload(Contract.student))
        .where(Contract.contract_number == normalized_contract_number)
    )
    contract = contract_result.scalar_one_or_none()

    if not contract:
        return {
            "error": {
                "code": PaymeError.INVALID_ACCOUNT,
                "message": {
                    "ru": "Договор с таким номером не найден",
                    "uz": "Bunday raqamli shartnoma topilmadi",
                    "en": "Contract with this number not found"
                },
                "data": "account.contract"
            },
            "id": request_id
        }

    if contract.status != ContractStatus.ACTIVE:
        return {
            "error": {
                "code": PaymeError.INVALID_ACCOUNT,
                "message": {
                    "ru": "Договор не активен",
                    "uz": "Shartnoma faol emas",
                    "en": "Contract is not active"
                },
                "data": "account.contract"
            },
            "id": request_id
        }

    # ✅ Amount tekshirish
    amount_sum = float(amount) / 100
    expected_amount = float(contract.monthly_fee)

    if amount_sum < expected_amount:
        return {
            "error": {
                "code": PaymeError.INVALID_AMOUNT,
                "message": {
                    "ru": f"Сумма должна быть не меньше {expected_amount}",
                    "uz": f"Summa kamida {expected_amount} bo'lishi kerak",
                    "en": f"Amount must be at least {expected_amount}"
                }
            },
            "id": request_id
        }

    # ✅ Payment Year va Month ni to'g'ri olish
    payment_year = account.get("payment_year")
    payment_month = account.get("payment_month")

    # ✅ Year validatsiyasi
    if not payment_year or payment_year == 0 or payment_year == "":
        payment_year = datetime.now().year
    else:
        try:
            payment_year = int(payment_year)
            # Yilni tekshirish
            if payment_year < 1900 or payment_year > 2100:
                payment_year = datetime.now().year
        except (TypeError, ValueError):
            return {
                "error": {
                    "code": PaymeError.INVALID_PARAMS,
                    "message": {
                        "ru": "Неверный год оплаты",
                        "uz": "Noto'g'ri to'lov yili",
                        "en": "Invalid payment year"
                    }
                },
                "id": request_id
            }

    # ✅ Month validatsiyasi
    if not payment_month or payment_month == 0 or payment_month == "":
        payment_month = datetime.now().month
    else:
        try:
            payment_month = int(payment_month)
            if not (1 <= payment_month <= 12):
                return {
                    "error": {
                        "code": PaymeError.INVALID_PARAMS,
                        "message": {
                            "ru": "Неверный месяц оплаты (должен быть 1-12)",
                            "uz": "Noto'g'ri to'lov oyi (1-12 oralig'ida bo'lishi kerak)",
                            "en": "Invalid payment month (must be 1-12)"
                        }
                    },
                    "id": request_id
                }
        except (TypeError, ValueError):
            return {
                "error": {
                    "code": PaymeError.INVALID_PARAMS,
                    "message": {
                        "ru": "Неверный месяц оплаты",
                        "uz": "Noto'g'ri to'lov oyi",
                        "en": "Invalid payment month"
                    }
                },
                "id": request_id
            }

    print(f"📅 Payment for: {payment_month}/{payment_year}")

    # ✅ Contract muddat tekshirish
    from datetime import date as date_class
    payment_date = date_class(payment_year, payment_month, 1)
    contract_start_month = date_class(contract.start_date.year, contract.start_date.month, 1)
    contract_end_month = date_class(contract.end_date.year, contract.end_date.month, 1)

    if payment_date < contract_start_month:
        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": f"Договор еще не начался. Начало: {contract.start_date.isoformat()}",
                    "uz": f"Shartnoma hali boshlanmagan. Boshlanishi: {contract.start_date.isoformat()}",
                    "en": f"Contract has not started yet. Start date: {contract.start_date.isoformat()}"
                }
            },
            "id": request_id
        }

    if payment_date > contract_end_month:
        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": f"Договор истек. Окончание: {contract.end_date.isoformat()}",
                    "uz": f"Shartnoma muddati tugagan. Tugash sanasi: {contract.end_date.isoformat()}",
                    "en": f"Contract has expired. End date: {contract.end_date.isoformat()}"
                }
            },
            "id": request_id
        }

    # ✅ Boshqa PENDING tranzaksiyalarni tekshirish
    other_pending_result = await db.execute(
        select(Transaction).where(
            Transaction.contract_id == contract.id,
            Transaction.status == PaymentStatus.PENDING,
            Transaction.payment_year == payment_year,
            cast(Transaction.payment_months, JSONB).op('@>')(cast([payment_month], JSONB)),
            Transaction.external_id != str(payme_id)
        )
    )
    other_pending_list = other_pending_result.scalars().all()

    if other_pending_list:
        print(f"⚠️ Found {len(other_pending_list)} other pending transactions")
        return {
            "error": {
                "code": PaymeError.INVALID_ACCOUNT,
                "message": {
                    "ru": "Для данного договора уже существует активная транзакция ожидания оплаты",
                    "uz": "Ushbu shartnoma uchun to'lov kutilayotgan faol tranzaksiya mavjud",
                    "en": "An active pending transaction already exists for this contract"
                },
                "data": "account.contract"
            },
            "id": request_id
        }

    # ✅ Allaqachon to'langan to'lovni tekshirish
    success_result = await db.execute(
        select(Transaction).where(
            Transaction.contract_id == contract.id,
            Transaction.status == PaymentStatus.SUCCESS,
            Transaction.payment_year == payment_year,
            cast(Transaction.payment_months, JSONB).op('@>')(cast([payment_month], JSONB))
        )
    )
    success_payment = success_result.scalar_one_or_none()

    if success_payment:
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
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": f"Оплата за {month_names_ru[payment_month]} {payment_year} уже существует",
                    "uz": f"{month_names_uz[payment_month]} {payment_year} uchun to'lov allaqachon mavjud",
                    "en": f"Payment for {month_names_en[payment_month]} {payment_year} already exists"
                }
            },
            "id": request_id
        }

    # ✅ Yangi tranzaksiya yaratish
    transaction = Transaction(
        external_id=str(payme_id),
        amount=expected_amount,
        source=PaymentSource.PAYME,
        status=PaymentStatus.PENDING,
        contract_id=contract.id,
        student_id=contract.student_id,
        payment_year=payment_year,
        payment_months=[payment_month],
        comment=f"Payme create: ID {payme_id}, month {payment_month}/{payment_year}"
    )

    db.add(transaction)

    try:
        await db.commit()
        await db.refresh(transaction)
        print(f"✅ Transaction created: id={transaction.id}, external_id={transaction.external_id}")
    except Exception as e:
        await db.rollback()
        print(f"❌ Error creating transaction: {e}")
        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": "Ошибка создания транзакции",
                    "uz": "Tranzaksiya yaratishda xatolik",
                    "en": "Error creating transaction"
                }
            },
            "id": request_id
        }

    # ✅ Javob qaytarish
    return create_success_response(
        {
            "create_time": int(transaction.created_at.timestamp() * 1000),
            "perform_time": 0,
            "cancel_time": 0,
            "transaction": str(transaction.id),
            "state": 1,
            "reason": None
        },
        request_id
    )


async def perform_transaction(params: dict, request_id: int, db: AsyncSession):
    payme_id = params.get("id")

    if not payme_id:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Неверные параметры",
                    "uz": "Noto'g'ri parametrlar",
                    "en": "Invalid parameters"
                }
            },
            "id": request_id
        }

    transaction_result = await db.execute(
        select(Transaction).where(
            Transaction.external_id == str(payme_id)
        )
    )
    transaction = transaction_result.scalar_one_or_none()

    if not transaction:
        return {
            "error": {
                "code": PaymeError.TRANSACTION_NOT_FOUND,
                "message": {
                    "ru": "Транзакция не найдена",
                    "uz": "Tranzaksiya topilmadi",
                    "en": "Transaction not found"
                }
            },
            "id": request_id
        }


    if transaction.status == PaymentStatus.SUCCESS:
        return create_success_response(
            {
                "create_time": int(transaction.created_at.timestamp() * 1000),
                "perform_time": int(transaction.paid_at.timestamp() * 1000) if transaction.paid_at else 0,
                "cancel_time": 0,
                "transaction": str(transaction.id),
                "state": 2,
                "reason": None
            },
            request_id
        )


    if transaction.status == PaymentStatus.CANCELLED:

        state = -2 if transaction.paid_at else -1


        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,  # -31008
                "message": {
                    "ru": "Транзакция отменена",
                    "uz": "Tranzaksiya bekor qilingan",
                    "en": "Transaction cancelled"
                }
            },
            "id": request_id
        }


    contract_result = await db.execute(
        select(Contract).where(Contract.id == transaction.contract_id)
    )
    contract = contract_result.scalar_one_or_none()

    if not contract:
        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": "Договор не найден",
                    "uz": "Shartnoma topilmadi",
                    "en": "Contract not found"
                }
            },
            "id": request_id
        }

    if contract.status != ContractStatus.ACTIVE:
        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": "Договор не активен",
                    "uz": "Shartnoma faol emas",
                    "en": "Contract is not active"
                }
            },
            "id": request_id
        }

    payment_year = transaction.payment_year
    payment_month = transaction.payment_months[0] if transaction.payment_months else datetime.now().month

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
        transaction.status = PaymentStatus.CANCELLED
        transaction.comment = f"Cancelled: duplicate payment for month {payment_month}/{payment_year}"
        await db.commit()

        return {
            "error": {
                "code": PaymeError.COULD_NOT_PERFORM,
                "message": {
                    "ru": "Оплата за этот месяц уже существует",
                    "uz": "Ushbu oy uchun to'lov allaqachon mavjud",
                    "en": "Payment for this month already exists"
                }
            },
            "id": request_id
        }


    transaction.status = PaymentStatus.SUCCESS
    transaction.paid_at = datetime.utcnow()
    transaction.comment = f"Payme confirmed: ID {payme_id}, month {payment_month}/{payment_year}"

    await db.commit()
    await db.refresh(transaction)


    return create_success_response(
        {
            "create_time": int(transaction.created_at.timestamp() * 1000),
            "perform_time": int(transaction.paid_at.timestamp() * 1000),
            "cancel_time": 0,
            "transaction": str(transaction.id),
            "state": 2,
            "reason": None
        },
        request_id
    )


async def check_transaction(params: dict, request_id: int, db: AsyncSession):
    payme_id = params.get("id")

    if not payme_id:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Неверные параметры",
                    "uz": "Noto'g'ri parametrlar",
                    "en": "Invalid parameters"
                }
            },
            "id": request_id
        }

    transaction_result = await db.execute(
        select(Transaction).where(
            (Transaction.external_id == str(payme_id)) |
            (cast(Transaction.id, String) == str(payme_id))
        )
    )

    transaction = transaction_result.scalar_one_or_none()

    if not transaction:
        return {
            "error": {
                "code": PaymeError.TRANSACTION_NOT_FOUND,
                "message": {
                    "ru": "Транзакция не найдена",
                    "uz": "Tranzaksiya topilmadi",
                    "en": "Transaction not found"
                }
            },
            "id": request_id
        }

    # SUCCESS
    if transaction.status == PaymentStatus.SUCCESS:
        return create_success_response(
            {
                "create_time": int(transaction.created_at.timestamp() * 1000),
                "perform_time": int(transaction.paid_at.timestamp() * 1000) if transaction.paid_at else 0,
                "cancel_time": 0,
                "transaction": str(transaction.id),
                "state": 2,
                "reason": None
            },
            request_id
        )


    if transaction.status == PaymentStatus.CANCELLED:
        state = -2 if transaction.paid_at else -1
        perform_time = int(transaction.paid_at.timestamp() * 1000) if transaction.paid_at else 0


        cancel_time = int(transaction.cancelled_at.timestamp() * 1000) if transaction.cancelled_at else 0


        reason = None
        if transaction.comment and "reason" in transaction.comment.lower():
            try:
                reason = int(transaction.comment.split("reason")[-1].strip())
            except:
                pass



        return create_success_response(
            {
                "create_time": int(transaction.created_at.timestamp() * 1000),
                "perform_time": perform_time,
                "cancel_time": cancel_time,
                "transaction": str(transaction.id),
                "state": state,
                "reason": reason
            },
            request_id
        )


    return create_success_response(
        {
            "create_time": int(transaction.created_at.timestamp() * 1000),
            "perform_time": 0,
            "cancel_time": 0,
            "transaction": str(transaction.id),
            "state": 1,
            "reason": None
        },
        request_id
    )


async def cancel_transaction(params: dict, request_id: int, db: AsyncSession):
    payme_id = params.get("id")
    reason = params.get("reason", 5)

    if not payme_id:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Неверные параметры",
                    "uz": "Noto'g'ri parametrlar",
                    "en": "Invalid parameters"
                }
            },
            "id": request_id
        }

    transaction_result = await db.execute(
        select(Transaction).where(
            Transaction.external_id == str(payme_id)
        )
    )
    transaction = transaction_result.scalar_one_or_none()

    if not transaction:
        return {
            "error": {
                "code": PaymeError.TRANSACTION_NOT_FOUND,
                "message": {
                    "ru": "Транзакция не найдена",
                    "uz": "Tranzaksiya topilmadi",
                    "en": "Transaction not found"
                }
            },
            "id": request_id
        }


    if transaction.status == PaymentStatus.CANCELLED:
        state = -2 if transaction.paid_at else -1
        perform_time = int(transaction.paid_at.timestamp() * 1000) if transaction.paid_at else 0


        cancel_time = int(transaction.cancelled_at.timestamp() * 1000) if transaction.cancelled_at else 0

        saved_reason = 5
        if transaction.comment and "reason" in transaction.comment.lower():
            try:
                reason_part = transaction.comment.split("reason")[-1].strip()
                saved_reason = int(reason_part)
            except (ValueError, IndexError):
                saved_reason = 5



        return create_success_response(
            {
                "create_time": int(transaction.created_at.timestamp() * 1000),
                "perform_time": perform_time,
                "cancel_time": cancel_time,
                "transaction": str(transaction.id),
                "state": state,
                "reason": saved_reason
            },
            request_id
        )


    state = -2 if transaction.paid_at else -1
    perform_time = int(transaction.paid_at.timestamp() * 1000) if transaction.paid_at else 0


    now = datetime.utcnow()
    cancel_time_ms = int(now.timestamp() * 1000)

    transaction.status = PaymentStatus.CANCELLED
    transaction.cancelled_at = now
    transaction.comment = f"Cancelled by Payme: reason {reason}"

    await db.commit()




    return create_success_response(
        {
            "create_time": int(transaction.created_at.timestamp() * 1000),
            "perform_time": perform_time,
            "cancel_time": cancel_time_ms,
            "transaction": str(transaction.id),
            "state": state,
            "reason": reason
        },
        request_id
    )


async def get_statement(params: dict, request_id: int, db: AsyncSession):
    """
    Payme hisobotlari uchun tranzaksiyalar ro'yxatini qaytarish

    Talablar:
    1. from <= created_at <= to
    2. Faqat CreateTransaction orqali yaratilgan tranzaksiyalar
    3. created_at bo'yicha o'sish tartibida saralash
    """
    from_time = params.get("from")
    to_time = params.get("to")

    if from_time is None or to_time is None:
        return {
            "error": {
                "code": PaymeError.INVALID_PARAMS,
                "message": {
                    "ru": "Неверные параметры",
                    "uz": "Noto'g'ri parametrlar",
                    "en": "Invalid parameters"
                }
            },
            "id": request_id
        }

    # Timestamp'larni datetime ga o'tkazish (milliseconds)
    from datetime import datetime as dt
    from_datetime = dt.fromtimestamp(from_time / 1000.0)
    to_datetime = dt.fromtimestamp(to_time / 1000.0)

    print(f"📊 GetStatement: from {from_datetime} to {to_datetime}")

    # Tranzaksiyalarni olish
    transactions_result = await db.execute(
        select(Transaction)
        .where(
            Transaction.source == PaymentSource.PAYME,
            Transaction.created_at >= from_datetime,
            Transaction.created_at <= to_datetime
        )
        .order_by(Transaction.created_at.asc())  # O'sish tartibida
    )
    transactions = transactions_result.scalars().all()

    print(f"✅ Found {len(transactions)} transactions")

    # Javobni tayyorlash
    transactions_list = []

    for trans in transactions:
        # Contract ma'lumotlarini olish
        contract_result = await db.execute(
            select(Contract).where(Contract.id == trans.contract_id)
        )
        contract = contract_result.scalar_one_or_none()

        # ✅ State aniqlash (paid_at ga qarab)
        if trans.status == PaymentStatus.SUCCESS:
            state = 2
        elif trans.status == PaymentStatus.CANCELLED:
            # ✅ MUHIM: paid_at tekshirish!
            state = -2 if trans.paid_at else -1
        else:
            state = 1

        # ✅ Perform time (faqat paid_at bo'lsa)
        perform_time = 0
        if trans.paid_at:
            perform_time = int(trans.paid_at.timestamp() * 1000)

        # ✅ Cancel time (cancelled_at dan olish!)
        cancel_time = 0
        if trans.status == PaymentStatus.CANCELLED:
            if trans.cancelled_at:
                cancel_time = int(trans.cancelled_at.timestamp() * 1000)
            elif trans.updated_at:
                cancel_time = int(trans.updated_at.timestamp() * 1000)

        # ✅ Reason (comment dan olish)
        reason = None
        if trans.status == PaymentStatus.CANCELLED:
            if trans.comment and "reason" in trans.comment.lower():
                try:
                    reason = int(trans.comment.split("reason")[-1].strip())
                except:
                    reason = 5
            else:
                reason = 5

        transactions_list.append({
            "id": trans.external_id,  # Payme ID
            "time": int(trans.created_at.timestamp() * 1000),  # Create time in Payme
            "amount": int(trans.amount),
            "account": {
                "contract": contract.contract_number if contract else "",
                "payment_year": trans.payment_year,
                "payment_month": trans.payment_months[0] if trans.payment_months else None
            },
            "create_time": int(trans.created_at.timestamp() * 1000),
            "perform_time": perform_time,  # ✅ 0 yoki timestamp
            "cancel_time": cancel_time,    # ✅ cancelled_at dan
            "transaction": str(trans.id),  # Bizning ID
            "state": state,                # ✅ paid_at ga qarab -1 yoki -2
            "reason": reason               # ✅ comment dan
        })

    return create_success_response(
        {
            "transactions": transactions_list
        },
        request_id
    )

