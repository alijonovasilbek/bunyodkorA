import logging
import re
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import and_, func, select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.models.domain import Contract
from app.models.enums import PaymentStatus, PaymentSettlementType
from app.models.finance import Transaction
from app.services.transaction_reporting import normalize_unique_months

logger = logging.getLogger(__name__)

BUTTON_VIEW_PAID_MONTHS = "To'langan oylarni ko'rish"
BUTTON_VIEW_PAID_MONTHS_UI = "📄 To'langan oylarni ko'rish"
AWAIT_CONTRACT_KEY = "await_contract_number"


CYRILLIC_TO_LATIN_MAP = {
    "А": "A", "а": "a",
    "Б": "B", "б": "b",
    "В": "V", "в": "v",
    "Г": "G", "г": "g",
    "Ғ": "G'", "ғ": "g'",
    "Д": "D", "д": "d",
    "Е": "E", "е": "e",
    "Ё": "YO", "ё": "yo",
    "Ж": "J", "ж": "j",
    "З": "Z", "з": "z",
    "И": "I", "и": "i",
    "Й": "Y", "й": "y",
    "К": "K", "к": "k",
    "Қ": "Q", "қ": "q",
    "Л": "L", "л": "l",
    "М": "M", "м": "m",
    "Н": "N", "н": "n",
    "О": "O", "о": "o",
    "П": "P", "п": "p",
    "Р": "R", "р": "r",
    "С": "S", "с": "s",
    "Т": "T", "т": "t",
    "У": "U", "у": "u",
    "Ў": "O'", "ў": "o'",
    "Ф": "F", "ф": "f",
    "Х": "X", "х": "x",
    "Ҳ": "H", "ҳ": "h",
    "Ц": "TS", "ц": "ts",
    "Ч": "CH", "ч": "ch",
    "Ш": "SH", "ш": "sh",
    "Щ": "SH", "щ": "sh",
    "Ъ": "'", "ъ": "'",
    "Ь": "", "ь": "",
    "Ы": "I", "ы": "i",
    "Э": "E", "э": "e",
    "Ю": "YU", "ю": "yu",
    "Я": "YA", "я": "ya",
}


def _normalize_apostrophes(value: str) -> str:
    return (
        value.replace("`", "'")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("ʼ", "'")
        .replace("ʻ", "'")
        .replace("´", "'")
    )


def _transliterate_cyrillic_to_latin(value: str) -> str:
    return "".join(CYRILLIC_TO_LATIN_MAP.get(char, char) for char in value)


def _normalize_contract_number(value: str) -> str:
    normalized = _normalize_apostrophes(value.strip())
    normalized = _transliterate_cyrillic_to_latin(normalized)
    normalized = normalized.upper()
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _normalize_text_key(value: str) -> str:
    normalized = _normalize_contract_number(value)
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[^A-Z0-9]", "", normalized)
    return normalized


def _format_amount(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral():
        return f"{int(quantized):,}".replace(",", " ")
    return f"{quantized:,.2f}".replace(",", " ")


def _build_transaction_status_text(transaction: Transaction) -> str:
    if transaction.settlement_type == PaymentSettlementType.WAIVER_SPRAVKA:
        comment = (transaction.comment or "").strip()
        if comment:
            short_comment = comment if len(comment) <= 60 else f"{comment[:57]}..."
            return f"🟨 SPRAVKA ({short_comment})"
        return "🟨 SPRAVKA"
    return "✅ MUVAFFAQIYATLI"


class StudentTelegramBotService:
    def __init__(self) -> None:
        self.application: Application | None = None

    async def start(self) -> None:
        token = (settings.TELEGRAM_STUDENT_BOT_TOKEN or "").strip()
        if not token:
            logger.info("Student Telegram bot is disabled: TELEGRAM_STUDENT_BOT_TOKEN not set")
            return
        if self.application is not None:
            return

        try:
            app = Application.builder().token(token).build()
            app.add_handler(CommandHandler("start", self._start))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))

            await app.initialize()
            await app.start()
            if app.updater is not None:
                await app.updater.start_polling(drop_pending_updates=True)

            self.application = app
            logger.info("Student Telegram bot started")
        except Exception:
            logger.exception("Failed to start student Telegram bot")
            self.application = None

    async def stop(self) -> None:
        app = self.application
        if app is None:
            return

        try:
            if app.updater is not None:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
            logger.info("Student Telegram bot stopped")
        except Exception:
            logger.exception("Failed to stop student Telegram bot")
        finally:
            self.application = None

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        context.user_data[AWAIT_CONTRACT_KEY] = False
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(BUTTON_VIEW_PAID_MONTHS_UI)]],
            resize_keyboard=True,
        )
        await update.message.reply_text(
            "👋 Assalomu alaykum!\n\nKerakli bo'limni tanlang:",
            reply_markup=keyboard,
        )

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or not update.message.text:
            return

        text = update.message.text.strip()
        text_key = _normalize_text_key(text)
        button_key = _normalize_text_key(BUTTON_VIEW_PAID_MONTHS)

        if text_key == button_key:
            context.user_data[AWAIT_CONTRACT_KEY] = True
            await update.message.reply_text(
                "🧾 Iltimos, shartnoma raqamini yuboring.\n"
                "Masalan: 14-2016B3"
            )
            return

        if context.user_data.get(AWAIT_CONTRACT_KEY):
            response_text = await self._build_contract_payments_response(text)
            context.user_data[AWAIT_CONTRACT_KEY] = False
            await update.message.reply_text(response_text)
            return

        await update.message.reply_text(
            "ℹ️ Iltimos, pastdagi tugmadan foydalaning:\n📄 To'langan oylarni ko'rish"
        )

    async def _build_contract_payments_response(self, contract_input: str) -> str:
        normalized_contract = _normalize_contract_number(contract_input)
        if not normalized_contract:
            return "⚠️ Shartnoma raqami kiritilmadi."

        contract, transactions = await self._find_contract_and_transactions(normalized_contract)
        if contract is None:
            return (
                "❌ Shartnoma topilmadi.\n"
                f"🔎 Qidirilgan raqam: {normalized_contract}"
            )

        if not transactions:
            return (
                f"📄 Shartnoma: {contract.contract_number}\n"
                "ℹ️ To'lov topilmadi."
            )

        month_entries: dict[tuple[int, int], list[tuple[Decimal, str]]] = defaultdict(list)
        unknown_entries: list[tuple[Decimal, str]] = []

        for transaction in transactions:
            status_text = _build_transaction_status_text(transaction)
            amount_decimal = Decimal(str(transaction.amount))
            if transaction.payment_year is None:
                unknown_entries.append((amount_decimal, status_text))
                continue

            months = normalize_unique_months(transaction.payment_months)
            if not months:
                unknown_entries.append((amount_decimal, status_text))
                continue

            per_month_amount = amount_decimal / Decimal(len(months))
            for month_num in months:
                month_entries[(transaction.payment_year, month_num)].append((per_month_amount, status_text))

        if not month_entries and not unknown_entries:
            return (
                f"📄 Shartnoma: {contract.contract_number}\n"
                "ℹ️ To'lov topilmadi."
            )

        total_amount = sum(
            (amount for entries in month_entries.values() for amount, _ in entries),
            Decimal("0"),
        ) + sum((amount for amount, _ in unknown_entries), Decimal("0"))
        lines = [
            "✅ Ma'lumot topildi",
            f"📄 Shartnoma: {contract.contract_number}",
            f"💰 Jami to'langan: {_format_amount(total_amount)} so'm",
            "🗓 Oylar bo'yicha (summa + status):",
        ]

        for year_value, month_value in sorted(month_entries.keys()):
            entries = month_entries[(year_value, month_value)]
            if len(entries) == 1:
                amount, status_text = entries[0]
                lines.append(
                    f"• {year_value}-{month_value:02d}: {_format_amount(amount)} so'm | status: {status_text}"
                )
                continue

            month_total = sum((amount for amount, _ in entries), Decimal("0"))
            lines.append(
                f"• {year_value}-{month_value:02d}: {_format_amount(month_total)} so'm | status: ARALASH"
            )
            for amount, status_text in entries:
                lines.append(f"  - {_format_amount(amount)} so'm | {status_text}")

        if unknown_entries:
            unknown_total = sum((amount for amount, _ in unknown_entries), Decimal("0"))
            lines.append(
                f"• ⚠️ Oy biriktirilmagan: {_format_amount(unknown_total)} so'm | status: ARALASH"
            )
            for amount, status_text in unknown_entries:
                lines.append(f"  - {_format_amount(amount)} so'm | {status_text}")

        return "\n".join(lines)

    async def _find_contract_and_transactions(
        self, normalized_contract: str
    ) -> tuple[Contract | None, list[Transaction]]:
        async with AsyncSessionLocal() as db:
            normalized_contract_expr = func.replace(
                func.upper(func.replace(Contract.contract_number, " ", "")),
                "’",
                "'",
            )
            contract_result = await db.execute(
                select(Contract).where(normalized_contract_expr == normalized_contract)
            )
            contract = contract_result.scalar_one_or_none()

            if contract is None:
                # Fallback scan with transliteration-based comparison for mixed scripts.
                fallback_result = await db.execute(
                    select(Contract.id, Contract.contract_number)
                )
                matched_contract_id = None
                for row in fallback_result.all():
                    if row.contract_number and _normalize_contract_number(row.contract_number) == normalized_contract:
                        matched_contract_id = row.id
                        break

                if matched_contract_id is not None:
                    contract_result = await db.execute(
                        select(Contract).where(Contract.id == matched_contract_id)
                    )
                    contract = contract_result.scalar_one_or_none()

            if contract is None:
                return None, []

            transaction_result = await db.execute(
                select(Transaction)
                .where(
                    and_(
                        Transaction.contract_id == contract.id,
                        Transaction.status == PaymentStatus.SUCCESS,
                    )
                )
                .order_by(
                    Transaction.payment_year.asc().nullslast(),
                    Transaction.paid_at.asc().nullslast(),
                    Transaction.created_at.asc(),
                )
            )
            transactions = transaction_result.scalars().all()
            return contract, transactions


student_telegram_bot_service = StudentTelegramBotService()
