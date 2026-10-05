# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import json
import io
from decimal import Decimal, InvalidOperation
from html import escape
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime, timedelta, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Generador visual oficial de la Academia.
# Las imágenes antiguas integradas en este archivo ya no se utilizan.
from matplotlib import pyplot as plt
from academy_visuals import BUILDERS as ACADEMY_VISUAL_BUILDERS
from academy_visuals import CAPTIONS as ACADEMY_VISUAL_CAPTIONS

# ============================================================
# CONFIGURACIÓN
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

REFERRALS_FILE = os.getenv(
    "REFERRALS_FILE",
    "referrals.json"
)

SUBSCRIPTIONS_FILE = os.getenv(
    "SUBSCRIPTIONS_FILE",
    "subscriptions.json"
)

SIGNALS_PRICE_USDT = 30
SIGNALS_DURATION_DAYS = 30

USDT_BEP20_ADDRESS = os.getenv(
    "USDT_BEP20_ADDRESS",
    ""
).strip()

ADMIN_TELEGRAM_ID = os.getenv(
    "ADMIN_TELEGRAM_ID",
    ""
).strip()

# ============================================================
# ONEROYAL
# Estas variables ya están configuradas en Deployka.
# ============================================================

ONEROYAL_IB_URL = os.getenv(
    "ONEROYAL_IB_URL",
    ""
).strip()

ONEROYAL_COPYTRADING_URL = os.getenv(
    "ONEROYAL_COPYTRADING_URL",
    ""
).strip()

# ============================================================
# ACADEMIA
# ============================================================

ACADEMY_NAME = "Academia Apex Quant"

# ============================================================
# PAGOS / BNB SMART CHAIN / BEP20
# ============================================================

PAYMENTS_FILE = os.getenv("PAYMENTS_FILE", "payments.json").strip()
WALLETS_FILE = os.getenv("WALLETS_FILE", "wallets.json").strip()
WITHDRAWALS_FILE = os.getenv("WITHDRAWALS_FILE", "withdrawals.json").strip()
CONSENTS_FILE = os.getenv("CONSENTS_FILE", "consents.json").strip()

BSCSCAN_API_KEY = os.getenv("BSCSCAN_API_KEY", "").strip()
BSC_RPC_URL = os.getenv(
    "BSC_RPC_URL",
    "https://bsc-dataseed1.binance.org/"
).strip()
BSC_CHAIN_ID = int(os.getenv("BSC_CHAIN_ID", "56"))
BSC_FINALITY_CONFIRMATIONS = int(
    os.getenv("BSC_FINALITY_CONFIRMATIONS", "3")
)

# USDT BEP20 oficial de BNB Smart Chain. Puede sobrescribirse por ENV.
USDT_CONTRACT_ADDRESS = os.getenv(
    "USDT_CONTRACT_ADDRESS",
    "0x55d398326f99059ff775485246999027b3197955"
).strip()
USDT_DECIMALS = int(os.getenv("USDT_DECIMALS", "18"))

AUTO_WITHDRAWALS_ENABLED = (
    os.getenv("AUTO_WITHDRAWALS_ENABLED", "false").strip().lower()
    in ("1", "true", "yes", "on")
)
WITHDRAWAL_PRIVATE_KEY = os.getenv(
    "WITHDRAWAL_PRIVATE_KEY",
    ""
).strip()
WITHDRAWAL_MIN_USDT = Decimal("10")
WITHDRAWAL_FEE_USDT = Decimal("0")

# ============================================================
# REFERIDOS / COMISIONES
# ============================================================

REFERRAL_COMMISSION_LEVELS = {
    1: Decimal("0.05"),
    2: Decimal("0.03"),
    3: Decimal("0.02"),
}

# ============================================================
# FINANCE CALENDAR
# ============================================================

FINANCE_CALENDAR_BASE = (
    "https://www.financecalendar.com/wp-json/fc/v1"
)

# ============================================================
# FUNCIONES GENERALES
# ============================================================

def is_admin(user_id):
    """Comprueba si el usuario es administrador."""
    return str(user_id) == str(ADMIN_TELEGRAM_ID)


# ============================================================
# REFERIDOS - ARCHIVO
# ============================================================

def load_referrals():
    """Carga los datos de referidos."""
    try:
        if not os.path.exists(REFERRALS_FILE):
            return {}

        with open(
            REFERRALS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except Exception as error:
        logger.error(
            "Error cargando referidos: %s",
            error
        )
        return {}


def save_referrals(data):
    """Guarda los datos de referidos."""
    try:
        directory = os.path.dirname(REFERRALS_FILE)

        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        temp_file = REFERRALS_FILE + ".tmp"

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            REFERRALS_FILE
        )

        return True

    except Exception as error:
        logger.error(
            "Error guardando referidos: %s",
            error
        )
        return False


# ============================================================
# SISTEMA DE REFERIDOS
# ============================================================

def register_referral(user_id, referred_by):
    """
    Registra un referido directo.

    Nivel 1:
    usuario que invitó directamente.

    Los niveles 2 y 3 se obtienen a partir
    de la estructura existente de referidos.
    """

    user_id = str(user_id)
    referred_by = str(referred_by)

    if user_id == referred_by:
        return False

    referrals = load_referrals()

    if user_id not in referrals:
        referrals[user_id] = {
            "referred_by": referred_by,
            "level_1": [],
            "level_2": [],
            "level_3": [],
            "paid_subscriptions": 0,
            "commissions": 0
        }

        save_referrals(referrals)
        return True

    return False


def process_referral_levels(user_id):
    """
    Procesa la estructura de niveles 1, 2 y 3.
    """

    user_id = str(user_id)

    referrals = load_referrals()

    if user_id not in referrals:
        return

    user_data = referrals[user_id]

    level_1 = []
    level_2 = []
    level_3 = []

    # --------------------------------------------------------
    # NIVEL 1
    # --------------------------------------------------------

    for uid, data in referrals.items():

        if uid == user_id:
            continue

        if str(data.get("referred_by", "")) == user_id:
            level_1.append(uid)

    # --------------------------------------------------------
    # NIVEL 2
    # --------------------------------------------------------

    for uid in level_1:

        for child_uid, data in referrals.items():

            if child_uid == user_id:
                continue

            if str(data.get("referred_by", "")) == str(uid):
                level_2.append(child_uid)

    # --------------------------------------------------------
    # NIVEL 3
    # --------------------------------------------------------

    for uid in level_2:

        for child_uid, data in referrals.items():

            if child_uid == user_id:
                continue

            if str(data.get("referred_by", "")) == str(uid):
                level_3.append(child_uid)

    user_data["level_1"] = list(dict.fromkeys(level_1))
    user_data["level_2"] = list(dict.fromkeys(level_2))
    user_data["level_3"] = list(dict.fromkeys(level_3))

    referrals[user_id] = user_data

    save_referrals(referrals)


def get_referral_levels(user_id):
    """Obtiene las listas de niveles 1, 2 y 3."""

    user_id = str(user_id)

    referrals = load_referrals()

    if user_id not in referrals:
        return [], [], []

    process_referral_levels(user_id)

    referrals = load_referrals()

    user_data = referrals.get(user_id, {})

    return (
        user_data.get("level_1", []),
        user_data.get("level_2", []),
        user_data.get("level_3", [])
    )


def get_referral_count(user_id):
    """Obtiene el total de referidos."""

    level_1, level_2, level_3 = get_referral_levels(user_id)

    return (
        len(level_1)
        + len(level_2)
        + len(level_3)
    )


# ============================================================
# MENÚ PRINCIPAL
# ============================================================

def main_menu(user_id=None):

    keyboard = [
        [
            InlineKeyboardButton(
                "📊 Mercados",
                callback_data="markets"
            ),
            InlineKeyboardButton(
                "📡 Señales",
                callback_data="signals"
            )
        ],
        [
            InlineKeyboardButton(
                "📋 CopyTrading",
                callback_data="copytrading"
            ),
            InlineKeyboardButton(
                "👥 Referidos",
                callback_data="referrals"
            )
        ],
        [
            InlineKeyboardButton(
                "🎓 Academia",
                callback_data="academy"
            ),
            InlineKeyboardButton(
                "💰 Billetera",
                callback_data="wallet"
            )
        ],
        [
            InlineKeyboardButton(
                "🟢 Broker OneRoyal",
                callback_data="broker_oneroyal"
            )
        ],
        [
            InlineKeyboardButton(
                "🌐 Idioma",
                callback_data="language"
            ),
            InlineKeyboardButton(
                "⚙️ Configuración",
                callback_data="settings"
            )
        ]
    ]

    if user_id is not None and is_admin(user_id):
        keyboard.append([
            InlineKeyboardButton(
                "🛠️ Administración",
                callback_data="admin_menu"
            )
        ])

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# COPYTRADING
# ============================================================

def copytrading_menu():

    keyboard = []

    # --------------------------------------------------------
    # COPYTRADING
    # --------------------------------------------------------

    if ONEROYAL_COPYTRADING_URL:

        keyboard.append([
            InlineKeyboardButton(
                "📈 Seguir Apex Quant",
                url=ONEROYAL_COPYTRADING_URL
            )
        ])

    else:

        keyboard.append([
            InlineKeyboardButton(
                "⚠️ CopyTrading no configurado",
                callback_data="copy_link_missing"
            )
        ])

    # --------------------------------------------------------
    # CUENTA ONEROYAL
    # --------------------------------------------------------

    if ONEROYAL_IB_URL:

        keyboard.append([
            InlineKeyboardButton(
                "🏦 Abrir cuenta OneRoyal",
                url=ONEROYAL_IB_URL
            )
        ])

    else:

        keyboard.append([
            InlineKeyboardButton(
                "⚠️ Enlace OneRoyal no configurado",
                callback_data="ib_link_missing"
            )
        ])

    # --------------------------------------------------------
    # INFORMACIÓN
    # --------------------------------------------------------

    keyboard.extend([
        [
            InlineKeyboardButton(
                "ℹ️ ¿Cómo funciona?",
                callback_data="copy_info"
            )
        ],
        [
            InlineKeyboardButton(
                "📝 Cómo registrarse",
                callback_data="copy_register"
            )
        ],
        [
            InlineKeyboardButton(
                "📚 Pasos para comenzar",
                callback_data="copy_steps"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ])

    return InlineKeyboardMarkup(keyboard)


async def show_copy_menu(query):

    text = (
        "📋 <b>COPYTRADING — APEX QUANT</b>\n\n"
        "Apex Quant utiliza CopyTrading para que "
        "los usuarios puedan seguir las operaciones "
        "de la estrategia desde su propia cuenta.\n\n"
        "🏦 Para utilizar el servicio necesitas "
        "una cuenta con OneRoyal.\n\n"
        "📈 Una vez registrada y configurada tu cuenta, "
        "podrás acceder al sistema de CopyTrading "
        "de Apex Quant.\n\n"
        "⚠️ <b>Importante:</b>\n"
        "El CopyTrading implica riesgo. Los resultados "
        "pasados no garantizan resultados futuros.\n\n"
        "👇 Utiliza las opciones disponibles para "
        "registrarte y comenzar."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=copytrading_menu()
    )


async def show_copy_info(query):

    text = (
        "ℹ️ <b>¿CÓMO FUNCIONA EL COPYTRADING?</b>\n\n"
        "El CopyTrading permite que las operaciones de una "
        "estrategia puedan replicarse en la cuenta de un usuario, "
        "según la configuración y las condiciones disponibles "
        "en la plataforma.\n\n"
        "🔄 <b>Funcionamiento general:</b>\n"
        "1️⃣ Registra y configura tu cuenta OneRoyal.\n"
        "2️⃣ Accede al servicio de CopyTrading.\n"
        "3️⃣ Busca y selecciona <b>Apex Quant</b>.\n"
        "4️⃣ Configura los parámetros de riesgo y tamaño de operación "
        "que permita la plataforma.\n"
        "5️⃣ Una vez conectada la cuenta, las operaciones de la estrategia "
        "pueden replicarse automáticamente según la configuración establecida.\n"
        "6️⃣ Supervisa periódicamente tu cuenta y verifica que la conexión "
        "y los parámetros continúen activos.\n\n"
        "📊 <b>El resultado puede variar</b> según el capital, configuración "
        "de riesgo, tamaño de las posiciones, ejecución y condiciones del mercado.\n\n"
        "⚠️ <b>Importante:</b>\n"
        "• El CopyTrading no garantiza beneficios.\n"
        "• Las operaciones pueden generar pérdidas.\n"
        "• El rendimiento pasado no garantiza resultados futuros.\n"
        "• Cada usuario es responsable de su cuenta y de la configuración "
        "de riesgo que utilice."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=copytrading_menu()
    )


async def show_copy_follow(query):

    text = (
        "📈 <b>SEGUIR APEX QUANT</b>\n\n"
        "Desde aquí puedes acceder al CopyTrading "
        "de Apex Quant.\n\n"
        "1️⃣ Pulsa <b>📈 Seguir Apex Quant</b>.\n"
        "2️⃣ Accede a la plataforma correspondiente.\n"
        "3️⃣ Sigue las instrucciones de conexión.\n"
        "4️⃣ Verifica que tu cuenta esté correctamente "
        "configurada.\n\n"
        "⚠️ Recuerda que el trading implica riesgo "
        "de pérdida de capital."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=copytrading_menu()
    )


async def show_copy_register(query):

    text = (
        "📝 <b>REGISTRO EN ONEROYAL</b>\n\n"
        "Para utilizar CopyTrading necesitas una "
        "cuenta con OneRoyal.\n\n"
        "🏦 <b>Paso 1:</b> Pulsa "
        "«Abrir cuenta OneRoyal».\n\n"
        "🧾 <b>Paso 2:</b> Completa el registro "
        "con tus datos.\n\n"
        "🪪 <b>Paso 3:</b> Completa la verificación "
        "de identidad (KYC), si corresponde.\n\n"
        "💼 <b>Paso 4:</b> Configura la cuenta "
        "adecuada para utilizar el servicio.\n\n"
        "📈 <b>Paso 5:</b> Después podrás acceder "
        "al CopyTrading de Apex Quant.\n\n"
        "⚠️ No deposites fondos que no estés dispuesto "
        "a perder."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=copytrading_menu()
    )


async def show_copy_steps(query):

    text = (
        "📚 <b>PASOS PARA COMENZAR</b>\n\n"
        "1️⃣ Registra tu cuenta OneRoyal.\n"
        "2️⃣ Completa el proceso KYC correspondiente.\n"
        "3️⃣ Configura tu cuenta de trading.\n"
        "4️⃣ Accede al servicio de CopyTrading.\n"
        "5️⃣ Busca y sigue a Apex Quant.\n"
        "6️⃣ Comprueba que la conexión esté activa.\n\n"
        "⚠️ El CopyTrading no garantiza beneficios. "
        "Las operaciones pueden generar pérdidas."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=copytrading_menu()
    )


# ============================================================
# AVISOS DE ENLACES NO CONFIGURADOS
# ============================================================

async def show_missing_copy_link(query):

    text = (
        "⚠️ <b>ENLACE DE COPYTRADING</b>\n\n"
        "El enlace de CopyTrading de Apex Quant "
        "no está disponible en este momento.\n\n"
        "Si eres administrador, verifica la variable "
        "<code>ONEROYAL_COPYTRADING_URL</code> "
        "en Deployka."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="copytrading"
                )
            ]
        ])
    )


async def show_missing_ib_link(query):

    text = (
        "⚠️ <b>ENLACE DE ONEROYAL</b>\n\n"
        "El enlace de registro de OneRoyal "
        "no está disponible en este momento.\n\n"
        "Si eres administrador, verifica la variable "
        "<code>ONEROYAL_IB_URL</code> "
        "en Deployka."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="copytrading"
                )
            ]
        ])
    )

# ============================================================
# BROKER ONEROYAL
# ============================================================

async def show_broker_oneroyal(query):

    text = (
        "🟢 <b>BROKER ONEROYAL</b>\n\n"
        "Apex Quant integra OneRoyal como broker dentro del ecosistema "
        "del proyecto. Desde aquí puedes consultar información general "
        "y acceder directamente al registro mediante el enlace IB de Apex Quant.\n\n"
        "⚡ <b>Cuentas ECN</b>\n"
        "OneRoyal ofrece opciones de cuenta orientadas a condiciones "
        "de ejecución y trading electrónico. Las condiciones concretas "
        "de cada cuenta, spreads, comisiones, requisitos y disponibilidad "
        "pueden variar según la jurisdicción y el tipo de cuenta.\n\n"
        "📊 <b>Plataformas e instrumentos</b>\n"
        "El registro permite acceder a los servicios y productos que "
        "OneRoyal tenga disponibles para tu jurisdicción. Antes de operar, "
        "revisa las condiciones oficiales de la cuenta que elijas.\n\n"
        "🔗 <b>Registro mediante Apex Quant</b>\n"
        "Utiliza el botón de abajo para registrarte con el enlace IB "
        "asociado a Apex Quant.\n\n"
        "⚠️ <b>Riesgo:</b> el trading de instrumentos financieros puede "
        "ocasionar pérdidas. Verifica las condiciones, costes y riesgos "
        "antes de depositar fondos o comenzar a operar."
    )

    keyboard = []

    if ONEROYAL_IB_URL:
        keyboard.append([
            InlineKeyboardButton(
                "🚀 Registrarme con OneRoyal",
                url=ONEROYAL_IB_URL
            )
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(
                "⚠️ Enlace OneRoyal no configurado",
                callback_data="ib_link_missing"
            )
        ])

    keyboard.extend([
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# MERCADOS
# ============================================================

async def markets_menu(query):

    keyboard = [
        [
            InlineKeyboardButton(
                "📅 Calendario económico",
                callback_data="calendar"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ]

    text = (
        "📊 <b>MERCADOS</b>\n\n"
        "Consulta el calendario económico y "
        "los principales eventos que pueden "
        "influir en los mercados financieros.\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_markets(query):
    await markets_menu(query)


# ============================================================
# CALENDARIO ECONÓMICO
# ============================================================

def today_date():
    return date.today()


def tomorrow_date():
    return date.today() + timedelta(days=1)


def week_dates():
    today = date.today()

    start = today
    end = today + timedelta(days=6)

    return start, end


async def calendar_menu(query):

    keyboard = [
        [
            InlineKeyboardButton(
                "📅 Hoy",
                callback_data="calendar_today"
            ),
            InlineKeyboardButton(
                "📅 Mañana",
                callback_data="calendar_tomorrow"
            )
        ],
        [
            InlineKeyboardButton(
                "📆 Esta semana",
                callback_data="calendar_week"
            )
        ],
        [
            InlineKeyboardButton(
                "🔴 Alto impacto",
                callback_data="calendar_high"
            )
        ],
        [
            InlineKeyboardButton(
                "💵 Por divisa",
                callback_data="calendar_currency"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data="calendar"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="markets"
            )
        ]
    ]

    text = (
        "📅 <b>CALENDARIO ECONÓMICO</b>\n\n"
        "Consulta eventos económicos programados "
        "que pueden influir en los mercados.\n\n"
        "🌎 Divisas disponibles:\n"
        "🇺🇸 USD\n"
        "🇪🇺 EUR\n"
        "🇬🇧 GBP\n"
        "🇯🇵 JPY\n"
        "🇨🇭 CHF\n"
        "🇨🇦 CAD\n"
        "🇦🇺 AUD\n"
        "🇳🇿 NZD\n\n"
        "⚠️ Los eventos económicos pueden generar "
        "movimientos importantes y volatilidad.\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_calendar(query):
    await calendar_menu(query)


# ============================================================
# OBTENER EVENTOS DEL CALENDARIO
# ============================================================

async def fetch_calendar_events(start_date, end_date=None):

    if end_date is None:
        end_date = start_date

    params = {
        "from": start_date.strftime("%Y-%m-%d"),
        "to": end_date.strftime("%Y-%m-%d"),
        "limit": 500
    }

    url = (
        FINANCE_CALENDAR_BASE
        + "/calendar?"
        + urlencode(params)
    )

    def load_data():

        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "ApexQuantBot/1.0"
                )
            }
        )

        with urlopen(
            request,
            timeout=20
        ) as response:

            raw_data = response.read()

            return json.loads(
                raw_data.decode("utf-8")
            )

    try:

        loop = asyncio.get_running_loop()

        data = await loop.run_in_executor(
            None,
            load_data
        )

        if isinstance(data, dict):

            if isinstance(
                data.get("events"),
                list
            ):
                return data["events"]

            if isinstance(
                data.get("data"),
                list
            ):
                return data["data"]

        if isinstance(data, list):
            return data

        return []

    except Exception as error:

        logger.error(
            "Error obteniendo calendario: %s",
            error
        )

        return None


# ============================================================
# OBTENER VALOR DE UN EVENTO
# ============================================================

def event_value(event, *keys):

    for key in keys:

        value = event.get(key)

        if value is not None and value != "":
            return value

    return ""


# ============================================================
# FORMATEAR EVENTO
# ============================================================

def format_calendar_event(event):

    name = event_value(
        event,
        "name",
        "title",
        "event"
    )

    currency = event_value(
        event,
        "currency",
        "country",
        "ccy"
    )

    impact = event_value(
        event,
        "impact",
        "importance"
    )

    event_date = event_value(
        event,
        "date",
        "datetime",
        "time_utc",
        "time_et"
    )

    consensus = event_value(
        event,
        "consensus",
        "forecast",
        "expected"
    )

    prior = event_value(
        event,
        "prior",
        "previous"
    )

    actual = event_value(
        event,
        "actual"
    )

    # --------------------------------------------------------
    # IMPACTO
    # --------------------------------------------------------

    impact_text = str(impact).lower()

    if impact_text == "high":
        impact_icon = "🔴"
        impact_label = "ALTO"

    elif impact_text == "medium":
        impact_icon = "🟠"
        impact_label = "MEDIO"

    elif impact_text == "low":
        impact_icon = "🟢"
        impact_label = "BAJO"

    else:
        impact_icon = "⚪"
        impact_label = (
            str(impact)
            if impact
            else "N/D"
        )

    # --------------------------------------------------------
    # MONEDA
    # --------------------------------------------------------

    if currency:
        currency_text = str(currency).upper()
    else:
        currency_text = "N/D"

    # --------------------------------------------------------
    # FECHA / HORA
    # --------------------------------------------------------

    if event_date:

        event_date_text = str(event_date)

        if "T" in event_date_text:

            event_date_text = (
                event_date_text
                .replace("T", " ")
            )

    else:

        event_date_text = "Hora no disponible"

    # --------------------------------------------------------
    # RESULTADOS
    # --------------------------------------------------------

    result_lines = []

    if consensus:
        result_lines.append(
            f"📊 Consenso: {consensus}"
        )

    if prior:
        result_lines.append(
            f"⏮️ Anterior: {prior}"
        )

    if actual:
        result_lines.append(
            f"✅ Actual: {actual}"
        )

    result_text = ""

    if result_lines:
        result_text = (
            "\n"
            + "\n".join(result_lines)
        )

    return (
        f"{impact_icon} <b>{impact_label}</b> | "
        f"<b>{currency_text}</b>\n"
        f"📰 {name or 'Evento económico'}\n"
        f"🕒 {event_date_text}"
        f"{result_text}"
    )


# ============================================================
# MOSTRAR EVENTOS
# ============================================================

async def show_events(
    query,
    start_date,
    end_date=None,
    title="📅 CALENDARIO",
    filter_high=False,
    currency=None
):

    events = await fetch_calendar_events(
        start_date,
        end_date
    )

    if events is None:

        text = (
            f"{title}\n\n"
            "⚠️ <b>No se pudo conectar con "
            "el calendario económico.</b>\n\n"
            "Pulsa 🔄 Actualizar para intentarlo "
            "nuevamente."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🔄 Actualizar",
                    callback_data="calendar"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="calendar"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    filtered_events = []

    for event in events:

        if not isinstance(event, dict):
            continue

        if filter_high:

            impact = str(
                event_value(
                    event,
                    "impact",
                    "importance"
                )
            ).lower()

            if impact != "high":
                continue

        if currency:

            event_currency = str(
                event_value(
                    event,
                    "currency",
                    "country",
                    "ccy"
                )
            ).upper()

            if event_currency != currency.upper():
                continue

        filtered_events.append(event)

    # --------------------------------------------------------
    # ORDENAR
    # --------------------------------------------------------

    filtered_events.sort(
        key=lambda event: str(
            event_value(
                event,
                "time_utc",
                "datetime",
                "date"
            )
        )
    )

    # --------------------------------------------------------
    # LÍMITE VISUAL
    # --------------------------------------------------------

    filtered_events = filtered_events[:30]

    if not filtered_events:

        text = (
            f"{title}\n\n"
            "📭 <b>No hay eventos disponibles "
            "para los filtros seleccionados.</b>\n\n"
            "Puedes actualizar o consultar "
            "otra fecha/divisa."
        )

    else:

        event_texts = []

        for event in filtered_events:

            event_texts.append(
                format_calendar_event(event)
            )

        text = (
            f"{title}\n\n"
            + "\n\n".join(event_texts)
            + "\n\n"
            "ℹ️ Fuente: FinanceCalendar.com"
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data="calendar"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Calendario",
                callback_data="calendar"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# CALENDARIO - HOY
# ============================================================

async def show_calendar_today(query):

    today = today_date()

    await show_events(
        query,
        today,
        today,
        title="📅 <b>EVENTOS DE HOY</b>"
    )


# ============================================================
# CALENDARIO - MAÑANA
# ============================================================

async def show_calendar_tomorrow(query):

    tomorrow = tomorrow_date()

    await show_events(
        query,
        tomorrow,
        tomorrow,
        title="📅 <b>EVENTOS DE MAÑANA</b>"
    )


# ============================================================
# CALENDARIO - SEMANA
# ============================================================

async def show_calendar_week(query):

    start, end = week_dates()

    await show_events(
        query,
        start,
        end,
        title="📆 <b>EVENTOS DE ESTA SEMANA</b>"
    )


# ============================================================
# CALENDARIO - ALTO IMPACTO
# ============================================================

async def show_calendar_high(query):

    start, end = week_dates()

    await show_events(
        query,
        start,
        end,
        title="🔴 <b>EVENTOS DE ALTO IMPACTO</b>",
        filter_high=True
    )


# ============================================================
# CALENDARIO - SELECCIÓN DE DIVISA
# ============================================================

async def currency_events(query):

    keyboard = [
        [
            InlineKeyboardButton(
                "🇺🇸 USD",
                callback_data="currency_USD"
            ),
            InlineKeyboardButton(
                "🇪🇺 EUR",
                callback_data="currency_EUR"
            )
        ],
        [
            InlineKeyboardButton(
                "🇬🇧 GBP",
                callback_data="currency_GBP"
            ),
            InlineKeyboardButton(
                "🇯🇵 JPY",
                callback_data="currency_JPY"
            )
        ],
        [
            InlineKeyboardButton(
                "🇨🇭 CHF",
                callback_data="currency_CHF"
            ),
            InlineKeyboardButton(
                "🇨🇦 CAD",
                callback_data="currency_CAD"
            )
        ],
        [
            InlineKeyboardButton(
                "🇦🇺 AUD",
                callback_data="currency_AUD"
            ),
            InlineKeyboardButton(
                "🇳🇿 NZD",
                callback_data="currency_NZD"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="calendar"
            )
        ]
    ]

    text = (
        "💵 <b>EVENTOS POR DIVISA</b>\n\n"
        "Selecciona la divisa que quieres "
        "consultar:"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# MOSTRAR EVENTOS POR DIVISA
# ============================================================

async def show_currency_events(
    query,
    currency
):

    start, end = week_dates()

    currency_flags = {
        "USD": "🇺🇸",
        "EUR": "🇪🇺",
        "GBP": "🇬🇧",
        "JPY": "🇯🇵",
        "CHF": "🇨🇭",
        "CAD": "🇨🇦",
        "AUD": "🇦🇺",
        "NZD": "🇳🇿"
    }

    flag = currency_flags.get(
        currency.upper(),
        "💵"
    )

    await show_events(
        query,
        start,
        end,
        title=(
            f"{flag} <b>EVENTOS {currency.upper()}</b>"
        ),
        currency=currency
    )


# ============================================================
# SEÑALES
# ============================================================

async def signals_menu(query):

    keyboard = [
        [
            InlineKeyboardButton(
                "📡 Suscribirme a Señales",
                callback_data="signals_subscribe"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Información de suscripción",
                callback_data="signals_info"
            )
        ],
        [
            InlineKeyboardButton(
                "🔎 Ver mi estado",
                callback_data="signals_status"
            )
        ],
        [
            InlineKeyboardButton(
                "📜 Términos y condiciones",
                callback_data="signals_terms"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ]

    text = (
        "📡 <b>SEÑALES APEX QUANT</b>\n\n"
        "Accede a las señales de trading de "
        "Apex Quant mediante una suscripción mensual.\n\n"
        f"💰 Precio: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
        f"📆 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
        "🌐 Red: <b>BEP20</b>\n\n"
        "⚠️ Las señales son información y análisis "
        "de mercado. No garantizan resultados."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


async def show_signals(query):

    await signals_menu(query)


# ============================================================
# SUBSCRIPTIONS
# ============================================================

def load_subscriptions():

    try:

        if not os.path.exists(SUBSCRIPTIONS_FILE):
            return {}

        with open(
            SUBSCRIPTIONS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except Exception as error:

        logger.error(
            "Error cargando suscripciones: %s",
            error
        )

        return {}


def save_subscriptions(data):

    try:

        directory = os.path.dirname(
            SUBSCRIPTIONS_FILE
        )

        if directory and not os.path.exists(
            directory
        ):
            os.makedirs(
                directory,
                exist_ok=True
            )

        temp_file = (
            SUBSCRIPTIONS_FILE + ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            SUBSCRIPTIONS_FILE
        )

        return True

    except Exception as error:

        logger.error(
            "Error guardando suscripciones: %s",
            error
        )

        return False


def get_subscription(user_id):

    user_id = str(user_id)

    subscriptions = load_subscriptions()

    return subscriptions.get(user_id)


def is_subscription_active(user_id):

    subscription = get_subscription(user_id)

    if not subscription:
        return False

    if not subscription.get(
        "active",
        False
    ):
        return False

    expires_at = subscription.get(
        "expires_at"
    )

    if not expires_at:
        return False

    try:

        expiration = datetime.fromisoformat(
            expires_at
        )

        if datetime.now() >= expiration:

            subscription["active"] = False

            subscriptions = load_subscriptions()

            subscriptions[str(user_id)] = subscription

            save_subscriptions(
                subscriptions
            )

            return False

        return True

    except Exception as error:

        logger.error(
            "Error comprobando suscripción: %s",
            error
        )

        return False


# ============================================================
# INFORMACIÓN DE SEÑALES + PAGOS AUTOMÁTICOS
# ============================================================

def _safe_decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _atomic_json_load(path):
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception as error:
        logger.error("Error cargando %s: %s", path, error)
        return {}


def _atomic_json_save(path, data):
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        temp_file = path + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temp_file, path)
        return True
    except Exception as error:
        logger.error("Error guardando %s: %s", path, error)
        return False


def load_payments():
    return _atomic_json_load(PAYMENTS_FILE)


def save_payments(data):
    return _atomic_json_save(PAYMENTS_FILE, data)


def load_wallets():
    return _atomic_json_load(WALLETS_FILE)


def save_wallets(data):
    return _atomic_json_save(WALLETS_FILE, data)


def load_withdrawals():
    return _atomic_json_load(WITHDRAWALS_FILE)


def save_withdrawals(data):
    return _atomic_json_save(WITHDRAWALS_FILE, data)


def load_consents():
    return _atomic_json_load(CONSENTS_FILE)


def save_consents(data):
    return _atomic_json_save(CONSENTS_FILE, data)


def get_wallet_balance(user_id):
    wallets = load_wallets()
    entry = wallets.get(str(user_id), {})
    return _safe_decimal(entry.get("balance", "0"))


def set_wallet_balance(user_id, balance):
    wallets = load_wallets()
    uid = str(user_id)
    entry = wallets.get(uid, {})
    entry["balance"] = str(max(Decimal("0"), balance))
    entry.setdefault("updated_at", datetime.now().isoformat())
    entry["updated_at"] = datetime.now().isoformat()
    wallets[uid] = entry
    return save_wallets(wallets)


def credit_wallet(user_id, amount, reason, reference=""):
    amount = _safe_decimal(amount)
    if amount <= 0:
        return False
    wallets = load_wallets()
    uid = str(user_id)
    entry = wallets.get(uid, {"balance": "0", "history": []})
    balance = _safe_decimal(entry.get("balance", "0")) + amount
    entry["balance"] = str(balance)
    entry.setdefault("history", [])
    entry["history"].append({
        "type": "credit",
        "amount": str(amount),
        "reason": reason,
        "reference": reference,
        "created_at": datetime.now().isoformat(),
    })
    wallets[uid] = entry
    return save_wallets(wallets)


def debit_wallet(user_id, amount, reason, reference=""):
    amount = _safe_decimal(amount)
    wallets = load_wallets()
    uid = str(user_id)
    entry = wallets.get(uid, {"balance": "0", "history": []})
    balance = _safe_decimal(entry.get("balance", "0"))
    if amount <= 0 or balance < amount:
        return False
    entry["balance"] = str(balance - amount)
    entry.setdefault("history", [])
    entry["history"].append({
        "type": "debit",
        "amount": str(amount),
        "reason": reason,
        "reference": reference,
        "created_at": datetime.now().isoformat(),
    })
    wallets[uid] = entry
    return save_wallets(wallets)


def _bscscan_request(params):
    if not BSCSCAN_API_KEY:
        return None, "BSCSCAN_API_KEY no configurada."
    params = dict(params)
    params["apikey"] = BSCSCAN_API_KEY
    url = "https://api.bscscan.com/api?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "ApexQuantBot/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        if str(data.get("status")) == "1":
            return data.get("result"), None
        return None, str(data.get("result") or data.get("message") or "BscScan error")
    except Exception as error:
        logger.error("Error consultando BscScan: %s", error)
        return None, str(error)


def _rpc_request(method, params):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")
    request = Request(
        BSC_RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ApexQuantBot/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("error"):
            return None
        return data.get("result")
    except Exception as error:
        logger.error("Error RPC BNB Chain: %s", error)
        return None


def _hex_to_int(value):
    try:
        return int(value, 16) if isinstance(value, str) else int(value)
    except Exception:
        return 0


def find_usdt_transfer(tx_hash):
    """Busca un pago USDT BEP20 recibido por la wallet de Apex Quant."""
    if not USDT_BEP20_ADDRESS or not USDT_CONTRACT_ADDRESS:
        return None, "Wallet o contrato USDT no configurado."

    tx_hash = tx_hash.strip()
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        return None, "TXID no válido. Debe ser un hash BNB Smart Chain de 66 caracteres."

    payments = load_payments()
    existing = payments.get(tx_hash.lower())
    if existing and existing.get("status") == "credited":
        return existing, "already_credited"

    result, error = _bscscan_request({
        "module": "account",
        "action": "tokentx",
        "contractaddress": USDT_CONTRACT_ADDRESS,
        "address": USDT_BEP20_ADDRESS,
        "page": 1,
        "offset": 100,
        "startblock": 0,
        "endblock": 999999999,
        "sort": "desc",
    })
    if result is None:
        return None, error or "No se pudieron consultar las transferencias."

    target_hash = tx_hash.lower()
    transfer = None
    for item in result:
        if str(item.get("hash", "")).lower() == target_hash:
            transfer = item
            break

    if not transfer:
        return None, "No se encontró un ingreso USDT BEP20 a la wallet indicada."

    if str(transfer.get("contractAddress", "")).lower() != USDT_CONTRACT_ADDRESS.lower():
        return None, "El contrato del token no coincide con el USDT configurado."

    if str(transfer.get("to", "")).lower() != USDT_BEP20_ADDRESS.lower():
        return None, "La transferencia no fue recibida por la wallet de Apex Quant."

    raw_value = _safe_decimal(transfer.get("value", "0"))
    amount = raw_value / (Decimal(10) ** USDT_DECIMALS)
    if amount <= 0:
        return None, "El importe de la transferencia no es válido."

    confirmations = _hex_to_int(transfer.get("confirmations", 0))
    if confirmations <= 0:
        latest_hex = _rpc_request("eth_blockNumber", [])
        latest = _hex_to_int(latest_hex)
        block = _hex_to_int(transfer.get("blockNumber", 0))
        if latest and block:
            confirmations = max(0, latest - block + 1)

    if confirmations < BSC_FINALITY_CONFIRMATIONS:
        return None, (
            f"La transacción existe, pero todavía tiene {confirmations} "
            f"confirmaciones. Se requieren {BSC_FINALITY_CONFIRMATIONS}."
        )

    return {
        "tx_hash": tx_hash,
        "from": transfer.get("from", ""),
        "to": transfer.get("to", ""),
        "amount": str(amount),
        "confirmations": confirmations,
        "block_number": transfer.get("blockNumber", ""),
        "token": transfer.get("tokenSymbol", "USDT"),
        "contract": transfer.get("contractAddress", ""),
    }, None


def activate_paid_subscription(user_id, payment):
    user_id = str(user_id)
    subscriptions = load_subscriptions()
    now = datetime.now()
    current = subscriptions.get(user_id, {})

    try:
        current_expiration = datetime.fromisoformat(current.get("expires_at", ""))
    except Exception:
        current_expiration = now

    start = current_expiration if current.get("active") and current_expiration > now else now
    expiration = start + timedelta(days=SIGNALS_DURATION_DAYS)
    subscriptions[user_id] = {
        "active": True,
        "activated_at": now.isoformat(),
        "expires_at": expiration.isoformat(),
        "duration_days": SIGNALS_DURATION_DAYS,
        "price_usdt": SIGNALS_PRICE_USDT,
        "payment_tx": payment["tx_hash"],
        "payment_amount": payment["amount"],
        "payment_network": "BNB Smart Chain / BEP20",
    }
    return save_subscriptions(subscriptions), expiration


def credit_referral_commissions(payer_id, amount, tx_hash):
    """Acredita 5% / 3% / 2% a los tres niveles de la estructura."""
    referrals = load_referrals()
    current = str(payer_id)
    paid_amount = _safe_decimal(amount)
    credited = []

    for level in (1, 2, 3):
        user = referrals.get(current, {})
        parent = str(user.get("referred_by", ""))
        if not parent or parent == current or parent not in referrals:
            break
        commission = (paid_amount * REFERRAL_COMMISSION_LEVELS[level]).quantize(Decimal("0.01"))
        if commission > 0:
            credit_wallet(parent, commission, f"Comisión referido nivel {level}", tx_hash)
            parent_data = referrals.get(parent, {})
            parent_data["commissions"] = str(
                _safe_decimal(parent_data.get("commissions", "0")) + commission
            )
            parent_data["paid_subscriptions"] = int(parent_data.get("paid_subscriptions", 0)) + 1
            referrals[parent] = parent_data
            credited.append({"user_id": parent, "level": level, "amount": str(commission)})
        current = parent

    save_referrals(referrals)
    return credited


async def signals_info(query):
    text = (
        "💳 <b>SUSCRIPCIÓN DE SEÑALES</b>\n\n"
        f"💰 Precio: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
        f"📆 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
        "🌐 Red: <b>USDT BEP20 / BNB Smart Chain</b>\n\n"
        "El pago puede verificarse automáticamente mediante el TXID.\n\n"
        "1️⃣ Envía exactamente el importe indicado.\n"
        "2️⃣ Usa la red BNB Smart Chain (BEP20).\n"
        "3️⃣ Pulsa <b>💳 Pagar / Verificar</b>.\n"
        "4️⃣ Introduce el TXID de la transacción.\n"
        "5️⃣ El bot comprobará token, wallet receptora, importe y confirmaciones.\n\n"
        "⚠️ Verifica la red y la dirección antes de enviar fondos."
    )
    keyboard = [
        [InlineKeyboardButton("📡 Suscribirme", callback_data="signals_subscribe")],
        [InlineKeyboardButton("🔙 Volver", callback_data="signals")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def signals_subscribe(query):
    user_id = query.from_user.id
    if is_subscription_active(user_id):
        subscription = get_subscription(user_id) or {}
        text = (
            "✅ <b>SUSCRIPCIÓN ACTIVA</b>\n\n"
            f"📆 Vencimiento: <b>{subscription.get('expires_at', 'N/D')}</b>"
        )
        keyboard = [[InlineKeyboardButton("🔎 Ver estado", callback_data="signals_status")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="signals")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    address = USDT_BEP20_ADDRESS or "⚠️ Wallet no configurada"
    text = (
        "📡 <b>ACTIVAR SEÑALES APEX QUANT</b>\n\n"
        f"💰 Precio: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
        "🌐 Red: <b>BNB Smart Chain / BEP20</b>\n"
        f"📆 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n\n"
        "💳 <b>Wallet receptora:</b>\n"
        f"<code>{escape(address)}</code>\n\n"
        "📌 Envía exactamente el importe indicado y conserva el TXID.\n"
        "Después pulsa <b>💳 Pagar / Verificar</b> para que el bot compruebe la transacción automáticamente.\n\n"
        "⚠️ Nunca envíes fondos por otra red."
    )
    keyboard = [
        [InlineKeyboardButton("💳 Pagar / Verificar", callback_data="payment_verify")],
        [InlineKeyboardButton("🔎 Ver estado", callback_data="signals_status")],
        [InlineKeyboardButton("🔙 Volver", callback_data="signals")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def payment_verify_info(query):
    address = USDT_BEP20_ADDRESS or "⚠️ Wallet no configurada"
    text = (
        "💳 <b>VERIFICACIÓN AUTOMÁTICA DE PAGO</b>\n\n"
        f"💰 Importe: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
        "🌐 Red: <b>BNB Smart Chain / BEP20</b>\n"
        f"📥 Wallet: <code>{escape(address)}</code>\n\n"
        "Usa el comando:\n"
        "<code>/verify TXID</code>\n\n"
        "El bot comprobará que la transferencia sea USDT, llegue a la wallet correcta, tenga el importe requerido y alcance las confirmaciones configuradas.\n\n"
        "⚠️ No compartas claves privadas ni frases semilla."
    )
    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="signals_subscribe")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def verify_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if not context.args:
        await update.message.reply_text(
            "💳 <b>VERIFICAR PAGO</b>\n\n"
            "Usa:\n<code>/verify TXID</code>",
            parse_mode="HTML"
        )
        return

    tx_hash = context.args[0].strip()
    payments = load_payments()
    key = tx_hash.lower()
    if key in payments and payments[key].get("status") == "credited":
        payment = payments[key]
        if str(payment.get("user_id")) != str(user.id):
            await update.message.reply_text("⚠️ Ese TXID ya fue utilizado por otra cuenta.")
            return
        await update.message.reply_text("✅ Este pago ya fue procesado y tu suscripción está registrada.")
        return

    payment, error = await asyncio.to_thread(find_usdt_transfer, tx_hash)
    if not payment:
        await update.message.reply_text(
            "❌ <b>No se pudo validar el pago todavía.</b>\n\n"
            f"{escape(str(error))}\n\n"
            "Puedes volver a intentarlo cuando la transacción tenga las confirmaciones necesarias.",
            parse_mode="HTML"
        )
        return

    amount = _safe_decimal(payment.get("amount"))
    if amount < Decimal(str(SIGNALS_PRICE_USDT)):
        await update.message.reply_text(
            f"❌ El pago recibido es de <b>{amount} USDT</b>. Se requieren <b>{SIGNALS_PRICE_USDT} USDT</b>.",
            parse_mode="HTML"
        )
        return

    payments[key] = {
        **payment,
        "user_id": str(user.id),
        "status": "credited",
        "verified_at": datetime.now().isoformat(),
    }
    if not save_payments(payments):
        await update.message.reply_text("❌ No se pudo registrar el pago de forma segura. No se activó la suscripción.")
        return

    saved, expiration = activate_paid_subscription(user.id, payment)
    if not saved:
        await update.message.reply_text("❌ El pago fue detectado, pero no se pudo guardar la suscripción. Contacta al administrador.")
        return

    credited = credit_referral_commissions(user.id, amount, tx_hash)
    text = (
        "🎉 <b>PAGO VERIFICADO Y SUSCRIPCIÓN ACTIVADA</b>\n\n"
        f"💰 Recibido: <b>{amount} USDT</b>\n"
        f"📆 Vencimiento: <b>{expiration.strftime('%Y-%m-%d %H:%M')}</b>\n"
        f"🔗 TXID: <code>{escape(tx_hash)}</code>\n\n"
        "📡 Ya puedes recibir las señales mientras tu suscripción esté activa."
    )
    await update.message.reply_text(text, parse_mode="HTML")

    if credited:
        logger.info("Comisiones acreditadas por %s: %s", tx_hash, credited)

async def signals_terms(query):
    text = (
        "⚠️ <b>TÉRMINOS Y CONDICIONES — SEÑALES APEX QUANT</b>\n\n"
        "1️⃣ La especulación en los mercados financieros conlleva riesgos, "
        "invierta sólo lo que está dispuesto a arriesgar.\n\n"
        "2️⃣ Las señales ofrecidas por ApexQuant no son garantía de ganancias, "
        "utilize una correcta gestión de riesgo con un lotaje acorde a su capital, "
        "resultados pasados no garantizan resultados futuros.\n\n"
        "3️⃣ Las señales están disponibles sólo días laborales del mercado.\n\n"
        "4️⃣ Los días no laborales, cierres, festivos, feriados o alguna razón "
        "que resulte en el cierre del mercado, no se enviarán señales.\n\n"
        "5️⃣ Sólo se enviarán señales cuando se cumplan las condiciones según "
        "la metodología de ApexQuant, de no cumplirse las condiciones, no se "
        "enviarán señales con el fin de evitar las sobre operaciones que resulten "
        "en pérdidas innecesarias.\n\n"
        "6️⃣ Al activar su suscripción usted acepta éstos términos y condiciones."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Volver a Señales",
                callback_data="signals"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Menú principal",
                callback_data="back_main"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
async def signals_status(query):
    user_id = query.from_user.id
    subscription = get_subscription(user_id)
    if not subscription:
        text = "📡 <b>ESTADO DE SEÑALES</b>\n\n❌ No tienes una suscripción activa."
    elif is_subscription_active(user_id):
        text = (
            "📡 <b>ESTADO DE SEÑALES</b>\n\n"
            "🟢 Estado: <b>ACTIVA</b>\n"
            f"📆 Vencimiento: <b>{subscription.get('expires_at', 'N/D')}</b>"
        )
    else:
        text = "📡 <b>ESTADO DE SEÑALES</b>\n\n🔴 Estado: <b>INACTIVA</b>"
    keyboard = [
        [InlineKeyboardButton("📡 Suscribirme", callback_data="signals_subscribe")],
        [InlineKeyboardButton("🔙 Volver", callback_data="signals")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ============================================================
# REFERIDOS
# ============================================================

def referrals_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "🔗 Mi enlace de referido",
                callback_data="referral_link"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Mis referidos",
                callback_data="referral_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 Comisiones",
                callback_data="referral_commissions"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def show_referrals(query):

    user_id = query.from_user.id

    total = get_referral_count(user_id)

    text = (
        "👥 <b>PROGRAMA DE REFERIDOS</b>\n\n"
        "Invita nuevos usuarios a Apex Quant "
        "utilizando tu enlace personal.\n\n"
        f"👥 Total de referidos: <b>{total}</b>\n\n"
        "💰 <b>Comisiones por suscripciones pagadas:</b>\n"
        "🥇 Nivel 1: <b>5%</b>\n"
        "🥈 Nivel 2: <b>3%</b>\n"
        "🥉 Nivel 3: <b>2%</b>\n\n"
        "📌 Los niveles se calculan según la "
        "estructura de referidos registrada."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=referrals_menu()
    )


# ============================================================
# ENLACE DE REFERIDO
# ============================================================

async def show_referral_link(query):

    try:

        bot = query.get_bot()

        username = getattr(
            bot,
            "username",
            None
        )

        if not username:

            bot_info = await bot.get_me()

            username = bot_info.username

        if not username:

            raise ValueError(
                "No se pudo obtener el username del bot"
            )

        user_id = query.from_user.id

        referral_link = (
            f"https://t.me/{username}"
            f"?start=ref_{user_id}"
        )

        text = (
            "🔗 <b>MI ENLACE DE REFERIDO</b>\n\n"
            "Comparte este enlace con las personas "
            "que quieras invitar a Apex Quant:\n\n"
            f"<code>{referral_link}</code>\n\n"
            "👥 Cuando una persona se registre mediante "
            "tu enlace, quedará asociada a tu estructura "
            "de referidos.\n\n"
            "💰 Las comisiones se generan sobre "
            "suscripciones pagadas según el nivel."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "📤 Compartir enlace",
                    url=(
                        "https://t.me/share/url?"
                        + urlencode({
                            "url": referral_link,
                            "text": (
                                "🚀 Únete a Apex Quant "
                                "y descubre nuestras "
                                "herramientas de trading."
                            )
                        })
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="referrals"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as error:

        logger.error(
            "Error generando enlace de referido: %s",
            error
        )

        await query.edit_message_text(
            "⚠️ No se pudo generar el enlace "
            "de referido en este momento.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="referrals"
                    )
                ]
            ])
        )


# ============================================================
# ESTADÍSTICAS DE REFERIDOS
# ============================================================

async def show_referral_stats(query):

    user_id = query.from_user.id

    level_1, level_2, level_3 = (
        get_referral_levels(user_id)
    )

    total = (
        len(level_1)
        + len(level_2)
        + len(level_3)
    )

    text = (
        "📊 <b>MIS REFERIDOS</b>\n\n"
        f"🥇 Nivel 1: <b>{len(level_1)}</b>\n"
        f"🥈 Nivel 2: <b>{len(level_2)}</b>\n"
        f"🥉 Nivel 3: <b>{len(level_3)}</b>\n\n"
        f"👥 Total: <b>{total}</b>\n\n"
        "💡 <b>Estructura de comisiones:</b>\n"
        "🥇 Nivel 1 → 5%\n"
        "🥈 Nivel 2 → 3%\n"
        "🥉 Nivel 3 → 2%"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=referrals_menu()
    )


# ============================================================
# COMISIONES
# ============================================================

async def show_referral_commissions(query):

    user_id = query.from_user.id

    referrals = load_referrals()

    user_data = referrals.get(
        str(user_id),
        {}
    )

    commissions = user_data.get(
        "commissions",
        0
    )

    text = (
        "💰 <b>MIS COMISIONES</b>\n\n"
        f"💵 Comisiones registradas: "
        f"<b>{commissions}</b> USDT\n\n"
        "📊 <b>Porcentaje por nivel:</b>\n"
        "🥇 Nivel 1 → <b>5%</b>\n"
        "🥈 Nivel 2 → <b>3%</b>\n"
        "🥉 Nivel 3 → <b>2%</b>\n\n"
        "📌 Las comisiones están relacionadas "
        "con suscripciones pagadas de usuarios "
        "dentro de tu estructura de referidos."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📊 Ver referidos",
                callback_data="referral_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="referrals"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# IDIOMA
# ============================================================

async def show_language(query):

    keyboard = [
        [
            InlineKeyboardButton(
                "🇪🇸 Español",
                callback_data="language_es"
            ),
            InlineKeyboardButton(
                "🇺🇸 English",
                callback_data="language_en"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ]

    text = (
        "🌐 <b>IDIOMA</b>\n\n"
        "Selecciona el idioma que quieres "
        "utilizar en Apex Quant:"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


async def set_language(query, language):

    if language == "es":

        text = (
            "🇪🇸 <b>IDIOMA SELECCIONADO</b>\n\n"
            "Has seleccionado <b>Español</b>.\n\n"
            "La interfaz principal de Apex Quant "
            "está disponible en español."
        )

    elif language == "en":

        text = (
            "🇺🇸 <b>LANGUAGE SELECTED</b>\n\n"
            "You selected <b>English</b>.\n\n"
            "The language preference has been received."
        )

    else:

        text = (
            "⚠️ Idioma no disponible."
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "🌐 Cambiar idioma",
                callback_data="language"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# CONFIGURACIÓN
# ============================================================

async def show_settings(query):

    user_id = query.from_user.id

    admin_status = (
        "🛠️ Administrador"
        if is_admin(user_id)
        else "👤 Usuario"
    )

    text = (
        "⚙️ <b>CONFIGURACIÓN</b>\n\n"
        f"🆔 ID de Telegram: "
        f"<code>{user_id}</code>\n\n"
        f"👤 Tipo de cuenta: <b>{admin_status}</b>\n\n"
        "📡 Señales: puedes consultar tu estado "
        "desde el menú de Señales.\n\n"
        "🌐 Idioma: puedes cambiarlo desde "
        "el menú de Idioma.\n\n"
        "⚠️ Apex Quant no garantiza resultados "
        "financieros. El trading implica riesgo."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🌐 Cambiar idioma",
                callback_data="language"
            )
        ],
        [
            InlineKeyboardButton(
                "📡 Estado de señales",
                callback_data="signals_status"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# ACADEMIA APEX QUANT
# ============================================================

ACADEMY_MODULES = {
    "m1": {
        "title": "📘 Módulo 1 — Fundamentos del Trading",
        "text": (
            "El trading consiste en analizar mercados financieros y ejecutar "
            "operaciones buscando aprovechar movimientos del precio. En este "
            "módulo conocerás los principales mercados, activos y participantes.\n\n"

            "📚 Conceptos básicos:\n"
            "• Forex, índices, materias primas, acciones y criptomonedas.\n"
            "• Compradores y vendedores.\n"
            "• Precio, spread, volatilidad y liquidez.\n"
            "• Órdenes de mercado y órdenes pendientes.\n"
            "• Stop Loss y Take Profit.\n"
            "• Apalancamiento y margen.\n\n"

            "🔎 ¿Qué significa cada concepto?\n\n"

            "💱 Forex:\n"
            "Mercado en el que se negocian pares de divisas, como GBP/USD o GBP/JPY. "
            "El precio representa la relación de valor entre una divisa y otra.\n\n"

            "📊 Índices:\n"
            "Instrumentos que representan el comportamiento de un conjunto de acciones "
            "o de un segmento de un mercado. US30 es un ejemplo de índice seguido dentro "
            "del ecosistema de Apex Quant.\n\n"

            "🛢️ Materias primas:\n"
            "Activos relacionados con recursos físicos, como petróleo, oro u otras "
            "materias primas. Su precio puede verse afectado por oferta, demanda y "
            "factores económicos o geopolíticos.\n\n"

            "🏢 Acciones:\n"
            "Representan una participación en una empresa. Su precio puede reaccionar "
            "a resultados empresariales, expectativas de crecimiento, noticias y condiciones "
            "generales del mercado.\n\n"

            "🪙 Criptomonedas:\n"
            "Activos digitales negociados en mercados específicos. Pueden presentar "
            "cambios de precio y volatilidad importantes.\n\n"

            "🟢 Compradores y vendedores:\n"
            "Son los participantes que generan órdenes de compra y venta. El movimiento "
            "del precio refleja el encuentro continuo entre oferta y demanda.\n\n"

            "💵 Precio:\n"
            "Es el valor al que un activo puede negociarse en un momento determinado. "
            "En un gráfico, su evolución permite estudiar estructura, tendencia, rangos "
            "y posibles zonas de interés.\n\n"

            "↔️ Spread:\n"
            "Es la diferencia entre el precio disponible para vender y el precio disponible "
            "para comprar. Representa un coste de transacción que puede variar según el "
            "instrumento y las condiciones del mercado.\n\n"

            "🌪️ Volatilidad:\n"
            "Describe la magnitud y velocidad con la que puede variar el precio. Una mayor "
            "volatilidad puede producir movimientos más amplios y también aumentar el riesgo "
            "de ejecución y de pérdida.\n\n"

            "💧 Liquidez:\n"
            "Hace referencia a la facilidad con la que pueden ejecutarse operaciones sin "
            "producir cambios excesivos en el precio. En análisis de mercado también se "
            "utiliza el término para estudiar zonas donde pueden concentrarse órdenes.\n\n"

            "⚡ Orden de mercado:\n"
            "Orden diseñada para ejecutarse inmediatamente al mejor precio disponible, "
            "según la liquidez existente en ese momento.\n\n"

            "📌 Orden pendiente:\n"
            "Orden colocada para ejecutarse si el precio alcanza una condición determinada, "
            "como un nivel de precio previamente establecido.\n\n"

            "🛑 Stop Loss (SL):\n"
            "Nivel definido para limitar la pérdida de una operación si el precio se mueve "
            "en contra de la hipótesis planteada.\n\n"

            "🎯 Take Profit (TP):\n"
            "Nivel establecido para cerrar una operación con un beneficio objetivo si el "
            "precio alcanza la zona prevista.\n\n"

            "⚙️ Apalancamiento:\n"
            "Permite controlar una posición de mayor tamaño utilizando una cantidad menor "
            "de capital como margen. También aumenta la exposición y puede amplificar las "
            "pérdidas, por lo que requiere una gestión de riesgo estricta.\n\n"

            "💼 Margen:\n"
            "Capital que el intermediario puede requerir para mantener abierta una posición "
            "apalancada. No debe confundirse con la pérdida máxima permitida.\n\n"

            "También aprenderás por qué una operación nunca debe considerarse "
            "garantizada y por qué la gestión del riesgo forma parte del proceso "
            "desde el primer día."
        ),
    },

    "m2": {
        "title": "📊 Módulo 2 — Análisis Técnico",
        "text": (
            "El análisis técnico estudia el comportamiento histórico del precio "
            "mediante gráficos, estructura, volumen e indicadores.\n\n"

            "📈 Elementos principales:\n"
            "• Velas japonesas.\n"
            "• Soportes y resistencias.\n"
            "• Tendencias y rangos.\n"
            "• Máximos y mínimos.\n"
            "• Volumen.\n"
            "• RSI 14.\n"
            "• Temporalidades.\n"
            "• Contexto del mercado.\n\n"

            "🔎 ¿Qué significa cada elemento?\n\n"

            "🕯️ Velas japonesas:\n"
            "Cada vela resume el movimiento del precio durante un período determinado "
            "y muestra apertura, máximo, mínimo y cierre. El cuerpo y las mechas ayudan "
            "a observar presión compradora, presión vendedora y rechazo de precios.\n\n"

            "🧱 Soportes:\n"
            "Zonas donde históricamente el precio ha encontrado presión compradora o "
            "donde una caída ha tenido dificultad para continuar. No son líneas exactas "
            "ni garantizan que el precio vaya a rebotar.\n\n"

            "🚧 Resistencias:\n"
            "Zonas donde históricamente el precio ha encontrado presión vendedora o "
            "dificultad para continuar subiendo. Al igual que un soporte, debe entenderse "
            "como una zona y no como una barrera infalible.\n\n"

            "📈 Tendencia:\n"
            "Dirección predominante del movimiento del precio. Puede estudiarse mediante "
            "la secuencia de máximos y mínimos y debe analizarse en la temporalidad utilizada.\n\n"

            "↔️ Rango:\n"
            "Situación en la que el precio oscila dentro de una zona relativamente definida "
            "sin establecer una dirección sostenida. Los extremos del rango pueden convertirse "
            "en referencias para estudiar liquidez y reacciones.\n\n"

            "🔝 Máximos y mínimos:\n"
            "Puntos relevantes donde el precio ha alcanzado un máximo o mínimo respecto al "
            "movimiento que lo rodea. Su secuencia permite estudiar la estructura del mercado.\n\n"

            "📊 Volumen:\n"
            "Mide la actividad negociada o, dependiendo del mercado y plataforma, una medida "
            "relacionada con la actividad de negociación. Puede ayudar a contextualizar "
            "movimientos, pero no debe interpretarse de forma aislada.\n\n"

            "📉 RSI 14:\n"
            "Indicador de momentum que compara la magnitud de movimientos alcistas y bajistas "
            "durante 14 períodos. Lecturas altas pueden indicar fuerte momentum y lecturas "
            "bajas pueden indicar presión bajista; una lectura de sobrecompra o sobreventa "
            "no significa por sí sola que el precio deba revertirse.\n\n"

            "⏱️ Temporalidades:\n"
            "Son los períodos que representa cada vela del gráfico, como M5, H1 o H4. "
            "Una misma estructura puede verse diferente según la temporalidad, por lo que "
            "el contexto debe mantenerse coherente entre ellas.\n\n"

            "🌐 Contexto del mercado:\n"
            "Es la combinación de información que rodea al movimiento actual del precio: "
            "estructura, tendencia o rango, liquidez, volatilidad, temporalidad y, cuando "
            "corresponde, factores fundamentales o eventos económicos.\n\n"

            "La finalidad no es utilizar muchos indicadores, sino aprender a "
            "leer el gráfico y comprender qué está haciendo el precio antes "
            "de buscar una posible entrada."
        ),
        "visual": "candles",
    },

    "m3": {
        "title": "📰 Módulo 3 — Análisis Fundamental",
        "text": (
            "El análisis fundamental estudia los factores económicos que pueden "
            "influir en los mercados y modificar la percepción de los participantes.\n\n"

            "🌍 Conceptos importantes:\n"
            "• Inflación y CPI.\n"
            "• Empleo y desempleo.\n"
            "• PIB.\n"
            "• Tipos de interés.\n"
            "• Decisiones de bancos centrales.\n"
            "• PMI y actividad económica.\n"
            "• Noticias de alto impacto.\n"
            "• Calendario económico.\n\n"

            "Una noticia puede aumentar la volatilidad y modificar la liquidez "
            "del mercado. Por eso el contexto fundamental debe estudiarse junto "
            "con la estructura del precio, sin asumir que una noticia garantiza "
            "una determinada dirección."
        ),
    },

    "m4": {
        "title": "🏦 Módulo 4 — Análisis Institucional",
        "text": (
            "El análisis institucional busca comprender cómo la liquidez, el "
            "desequilibrio y el desplazamiento del precio pueden formar parte "
            "de la dinámica de los grandes participantes del mercado.\n\n"

            "🏦 Conceptos estudiados:\n"
            "• Liquidez.\n"
            "• Desplazamientos.\n"
            "• Desequilibrios.\n"
            "• Premium y Discount.\n"
            "• Zonas de interés.\n"
            "• Order Blocks.\n"
            "• Fair Value Gaps.\n"
            "• Barridos de liquidez.\n\n"

            "🔎 ¿Qué significa cada concepto?\n\n"

            "💧 Liquidez:\n"
            "En este contexto se refiere a zonas donde pueden existir concentraciones "
            "de órdenes. Generalmente puede encontrarse alrededor de máximos y mínimos "
            "visibles, Equal Highs, Equal Lows, extremos de rangos y otros niveles que "
            "muchos participantes pueden observar. Estas zonas pueden estudiarse como "
            "posibles objetivos del precio, pero no implican que necesariamente serán tomadas.\n\n"

            "🚀 Desplazamiento:\n"
            "Movimiento relativamente rápido y decidido del precio, normalmente caracterizado "
            "por velas amplias y una salida clara de una zona. Puede proporcionar información "
            "sobre un cambio en el equilibrio entre compradores y vendedores.\n\n"

            "⚖️ Desequilibrio:\n"
            "Situación en la que el precio se desplaza con rapidez y deja una zona en la que "
            "la negociación relativa ha sido menor frente al movimiento posterior. Los FVG "
            "son una forma concreta de estudiar este tipo de desequilibrio.\n\n"

            "🔺 Premium:\n"
            "Zona situada en la parte superior de un rango de referencia. En metodologías que "
            "utilizan Premium/Discount, se estudia como un área donde el precio se encuentra "
            "relativamente elevado dentro de ese rango.\n\n"

            "🔻 Discount:\n"
            "Zona situada en la parte inferior de un rango de referencia. Se estudia como un "
            "área donde el precio se encuentra relativamente bajo dentro de ese rango.\n\n"

            "🎯 Zonas de interés:\n"
            "Áreas del gráfico que merecen atención por la combinación de factores como "
            "estructura, liquidez, desplazamiento, OB, FVG, soporte o resistencia. Una zona "
            "de interés no equivale automáticamente a una entrada.\n\n"

            "🟦 Order Block (OB):\n"
            "Zona asociada a una vela o conjunto de velas inmediatamente anterior a un "
            "desplazamiento relevante. Para considerarlo una zona de mayor interés, debe "
            "existir contexto y una reacción o desplazamiento posterior que le dé relevancia. "
            "Un simple bloque de velas sin desplazamiento ni contexto no debe tratarse "
            "automáticamente como un Order Block válido.\n\n"

            "🟩 Fair Value Gap (FVG):\n"
            "Desequilibrio de tres velas en el que existe una separación entre el rango de "
            "la primera y la tercera vela, dejando una zona con poca interacción relativa "
            "durante el desplazamiento. Un FVG es más relevante cuando aparece acompañado "
            "por desplazamiento y contexto estructural. No todo hueco visual debe considerarse "
            "un FVG de calidad.\n\n"

            "🧹 Barrido de liquidez:\n"
            "Movimiento en el que el precio atraviesa un máximo, mínimo o agrupación de "
            "liquidez visible y posteriormente puede reaccionar o desplazarse en sentido "
            "contrario. El barrido por sí solo no confirma una entrada.\n\n"

            "El objetivo es comprender cómo relacionar estos conceptos con "
            "estructura y contexto, evitando utilizar una sola señal de manera aislada."
        ),
        "visual": "institutional",
    },

    "m5": {
        "title": "🧩 Módulo 5 — Estructura de Mercado",
        "text": (
            "La estructura permite estudiar la secuencia de máximos y mínimos "
            "para determinar cómo se está comportando el precio.\n\n"

            "📐 Conceptos principales:\n"
            "• HH — Higher High.\n"
            "• HL — Higher Low.\n"
            "• LH — Lower High.\n"
            "• LL — Lower Low.\n"
            "• BOS — Break of Structure.\n"
            "• CHOCH — Change of Character.\n"
            "• Tendencia y consolidación.\n"
            "• Cambios de estructura.\n\n"

            "🔎 ¿Qué significa cada concepto?\n\n"

            "🔝 HH — Higher High:\n"
            "Máximo más alto que el máximo estructural anterior. Una secuencia de HH, "
            "acompañada de mínimos crecientes, puede formar parte de una estructura alcista.\n\n"

            "🔼 HL — Higher Low:\n"
            "Mínimo que queda por encima del mínimo estructural anterior. Una sucesión de "
            "HL ayuda a identificar la permanencia de una estructura alcista mientras se "
            "mantenga el contexto que la sostiene.\n\n"

            "🔻 LH — Lower High:\n"
            "Máximo que queda por debajo del máximo estructural anterior. Forma parte de "
            "una secuencia que puede caracterizar una estructura bajista.\n\n"

            "🔽 LL — Lower Low:\n"
            "Mínimo más bajo que el mínimo estructural anterior. Una sucesión de LL junto "
            "con máximos decrecientes puede formar parte de una estructura bajista.\n\n"

            "💥 BOS — Break of Structure:\n"
            "Ruptura de un punto estructural relevante en la dirección del movimiento que "
            "se está desarrollando. Para darle mayor significado debe observarse qué nivel "
            "fue roto, en qué temporalidad y con qué contexto. Una simple mecha o ruptura "
            "sin contexto no debe interpretarse automáticamente como un BOS de alta calidad.\n\n"

            "🔄 CHOCH — Change of Character:\n"
            "Concepto utilizado para describir una alteración relevante en el comportamiento "
            "de la estructura, especialmente cuando el precio rompe una secuencia que venía "
            "dominando el movimiento. Debe estudiarse junto con los swings y el contexto; "
            "no toda ruptura pequeña representa un cambio completo de tendencia.\n\n"

            "📈 Tendencia:\n"
            "Movimiento direccional en el que existe una secuencia relativamente consistente "
            "de máximos y mínimos. La estructura alcista suele presentar HH/HL y la bajista "
            "LH/LL.\n\n"

            "↔️ Consolidación:\n"
            "Período en el que el precio permanece dentro de una zona y no desarrolla una "
            "secuencia direccional clara. Dentro de una consolidación pueden formarse zonas "
            "de liquidez en sus extremos.\n\n"

            "🔄 Cambio de estructura:\n"
            "Modificación de la secuencia previa de máximos y mínimos. Para estudiarlo "
            "correctamente es necesario diferenciar una ruptura menor de una ruptura de un "
            "swing estructural relevante y considerar la temporalidad utilizada.\n\n"

            "Una lectura estructural debe considerar la temporalidad utilizada "
            "y el contexto general. Una ruptura aislada no necesariamente significa "
            "que toda la estructura haya cambiado."
        ),
        "visual": "structure",
    },

    "m6": {
        "title": "💧 Módulo 6 — Liquidez y Flujo del Precio",
        "text": (
            "La liquidez representa zonas donde pueden concentrarse órdenes y "
            "donde el precio puede reaccionar o desplazarse con mayor intensidad.\n\n"

            "💧 Conceptos:\n"
            "• Highs y Lows.\n"
            "• Equal Highs y Equal Lows.\n"
            "• Liquidity Pools.\n"
            "• Buy-side liquidity.\n"
            "• Sell-side liquidity.\n"
            "• Liquidity Sweep.\n"
            "• Barridos de máximos y mínimos.\n"
            "• Desplazamiento posterior a la toma de liquidez.\n\n"

            "🔎 ¿Qué significa cada concepto y dónde suele encontrarse?\n\n"

            "🔝 Highs:\n"
            "Máximos relevantes del precio. La liquidez compradora puede concentrarse "
            "por encima de máximos visibles porque allí pueden ubicarse órdenes de stop "
            "de posiciones cortas y órdenes de compra condicionadas.\n\n"

            "🔻 Lows:\n"
            "Mínimos relevantes del precio. La liquidez vendedora puede concentrarse "
            "por debajo de mínimos visibles porque allí pueden ubicarse stops de posiciones "
            "largas y órdenes de venta condicionadas.\n\n"

            "🟰 Equal Highs (EQH):\n"
            "Dos o más máximos situados aproximadamente en el mismo nivel. Al ser una "
            "referencia visual evidente, pueden convertirse en una zona donde se estudie "
            "la posible concentración de liquidez por encima de esos máximos.\n\n"

            "🟰 Equal Lows (EQL):\n"
            "Dos o más mínimos situados aproximadamente en el mismo nivel. Pueden formar "
            "una zona de interés donde se estudie liquidez por debajo de esos mínimos.\n\n"

            "💧 Liquidity Pool:\n"
            "Agrupación o zona donde pueden concentrarse órdenes relacionadas con niveles "
            "de precio observables. Puede aparecer alrededor de máximos, mínimos, EQH, EQL, "
            "extremos de rangos y otros niveles que muchos participantes pueden identificar.\n\n"

            "🟢 Buy-side Liquidity (BSL):\n"
            "Liquidez que suele estudiarse por encima de máximos relevantes. Puede estar "
            "relacionada con stops de vendedores y órdenes de compra condicionadas. No "
            "significa que todas esas órdenes estén necesariamente visibles o presentes "
            "en una cantidad conocida.\n\n"

            "🔴 Sell-side Liquidity (SSL):\n"
            "Liquidez que suele estudiarse por debajo de mínimos relevantes. Puede estar "
            "relacionada con stops de compradores y órdenes de venta condicionadas.\n\n"

            "🧹 Liquidity Sweep:\n"
            "Movimiento en el que el precio atraviesa una zona de liquidez visible y "
            "posteriormente muestra una reacción o desplazamiento. El término no implica "
            "por sí solo que todas las órdenes de esa zona hayan sido ejecutadas.\n\n"

            "↕️ Barrido de máximos y mínimos:\n"
            "Un barrido de máximos ocurre cuando el precio supera un máximo relevante; "
            "un barrido de mínimos ocurre cuando cae por debajo de un mínimo relevante. "
            "Después debe observarse la reacción del precio y la estructura antes de "
            "considerar cualquier interpretación adicional.\n\n"

            "🚀 Desplazamiento posterior a la toma de liquidez:\n"
            "Movimiento decidido que aparece después de atravesar una zona de liquidez. "
            "Cuando existe un desplazamiento claro y una ruptura estructural coherente, "
            "puede aportar más información que el barrido aislado.\n\n"

            "📍 ¿Dónde suele encontrarse la liquidez?\n"
            "Generalmente se estudia alrededor de máximos y mínimos visibles, Equal Highs, "
            "Equal Lows, extremos de rangos, zonas donde el precio ha dejado estructuras "
            "muy evidentes y niveles que muchos participantes pueden utilizar para colocar "
            "stops u órdenes condicionadas. Estas zonas deben tratarse como áreas de estudio, "
            "no como niveles con liquidez garantizada.\n\n"

            "La liquidez debe analizarse dentro del contexto de la estructura. "
            "Un barrido por sí solo no constituye una confirmación automática "
            "de entrada."
        ),
        "visual": "liquidity",
    },

    "m7": {
        "title": "🟦 Módulo 7 — Order Blocks y Fair Value Gaps",
        "text": (
            "Los Order Blocks y Fair Value Gaps son conceptos utilizados para "
            "identificar zonas de interés dentro del movimiento del precio.\n\n"

            "🟦 Order Block (OB):\n"
            "Zona asociada a una vela o conjunto de velas inmediatamente anterior a un "
            "desplazamiento relevante. Se utiliza como referencia para estudiar una posible "
            "reacción posterior del precio.\n\n"

            "✅ ¿Cuándo puede considerarse válido un Order Block?\n"
            "Un OB adquiere mayor relevancia cuando está asociado a un desplazamiento claro, "
            "participa en una ruptura estructural relevante o aparece en un contexto donde "
            "liquidez y estructura aportan una razón adicional para estudiarlo. La zona debe "
            "definirse de forma coherente con la metodología utilizada y su invalidación "
            "debe estar previamente determinada.\n\n"

            "⚠️ ¿Qué NO convierte automáticamente una zona en OB?\n"
            "Una vela alcista o bajista aislada no es automáticamente un Order Block. "
            "Si no existe desplazamiento, contexto estructural o una razón clara para "
            "considerar esa zona relevante, debe evitarse etiquetarla simplemente como OB.\n\n"

            "🟩 Fair Value Gap (FVG):\n"
            "Desequilibrio de tres velas generado por un desplazamiento en el que queda "
            "una separación entre el rango de la primera y la tercera vela, dejando una "
            "zona con poca interacción relativa durante ese movimiento.\n\n"

            "✅ ¿Cuándo puede considerarse válido un FVG?\n"
            "Debe existir la configuración de tres velas correspondiente y una separación "
            "real entre los rangos que forman el desequilibrio. Su relevancia aumenta cuando "
            "aparece junto a un desplazamiento claro y dentro de un contexto estructural "
            "coherente.\n\n"

            "⚠️ ¿Qué NO convierte automáticamente una zona en FVG?\n"
            "No toda separación visual, mecha o movimiento rápido debe etiquetarse como FVG. "
            "Primero debe comprobarse que la estructura de tres velas cumple la definición "
            "utilizada y después evaluar el contexto.\n\n"

            "🔗 OB + FVG:\n"
            "Cuando ambas zonas aparecen relacionadas con un mismo desplazamiento y además "
            "coinciden con estructura, liquidez y temporalidad coherentes, pueden estudiarse "
            "como una confluencia. Aun así, ninguna combinación garantiza una reacción futura.\n\n"

            "La utilidad aumenta cuando OB/FVG se combinan con estructura, liquidez, "
            "temporalidad y contexto. Ninguno de estos conceptos garantiza por sí "
            "solo una reacción del mercado."
        ),
        "visual": "fvg_ob",
    },

    "m8": {
        "title": "⏱️ Módulo 8 — Estilos de Trading",
        "text": (
            "Existen diferentes formas de operar según el horizonte temporal "
            "y la duración de las posiciones.\n\n"
            "🥷 Scalping:\n"
            "Operaciones de muy corta duración, normalmente enfocadas en movimientos "
            "pequeños del precio.\n\n"
            "📅 Day Trading:\n"
            "Las posiciones se abren y cierran durante la misma jornada.\n\n"
            "🌊 Swing Trading:\n"
            "Busca movimientos que pueden durar varios días o semanas.\n\n"
            "🏛️ Position Trading:\n"
            "Trabaja con tesis de mayor plazo y movimientos más amplios.\n\n"
            "Cada estilo requiere una metodología, gestión del riesgo y planificación "
            "adaptadas a su horizonte temporal."
        ),
    },

    "m9": {
        "title": "🛡️ Módulo 9 — Gestión de Riesgo",
        "text": (
            "La gestión de riesgo busca limitar el impacto de las operaciones "
            "perdedoras y proteger el capital durante una serie de resultados.\n\n"
            "🛡️ Elementos fundamentales:\n"
            "• Riesgo por operación.\n"
            "• Tamaño de posición.\n"
            "• Stop Loss.\n"
            "• Take Profit.\n"
            "• Relación riesgo/beneficio.\n"
            "• Drawdown.\n"
            "• Pérdida máxima.\n"
            "• Correlación entre posiciones.\n"
            "• Exposición total.\n\n"
            "Una estrategia puede atravesar operaciones perdedoras. La gestión "
            "del riesgo busca evitar que una operación individual o una secuencia "
            "desfavorable comprometa de forma excesiva la cuenta."
        ),
    },

    "m10": {
        "title": "🧠 Módulo 10 — Psicología y Disciplina",
        "text": (
            "La ejecución de una metodología también implica controlar la forma "
            "en que se toman decisiones antes, durante y después de una operación.\n\n"
            "🧠 Aspectos importantes:\n"
            "• Disciplina.\n"
            "• Paciencia.\n"
            "• Control de impulsos.\n"
            "• Evitar el revenge trading.\n"
            "• Evitar el overtrading.\n"
            "• Seguir un plan previamente definido.\n"
            "• Aceptar operaciones perdedoras.\n"
            "• Mantener un diario de trading.\n\n"
            "La disciplina consiste en ejecutar un proceso definido incluso cuando "
            "el resultado de una operación individual no coincide con la expectativa."
        ),
    },

    "m11": {
        "title": "🔬 Módulo 11 — Construcción de un Análisis",
        "text": (
            "Una metodología puede organizarse mediante un proceso de análisis "
            "de varias etapas, comenzando por el contexto y terminando con una "
            "decisión de ejecución o de espera.\n\n"
            "🔎 Flujo de análisis:\n"
            "1️⃣ Contexto de mercado.\n"
            "2️⃣ Temporalidad superior.\n"
            "3️⃣ Dirección y estructura.\n"
            "4️⃣ Identificación de liquidez.\n"
            "5️⃣ Búsqueda de BOS o CHOCH.\n"
            "6️⃣ Identificación de OB/FVG.\n"
            "7️⃣ Confirmación en temporalidad inferior.\n"
            "8️⃣ Definición de invalidación.\n"
            "9️⃣ Cálculo del riesgo.\n"
            "🔟 Ejecución o espera.\n\n"
            "El análisis también puede complementarse con volumen, calendario "
            "económico y sesiones de mercado."
        ),
        "visual": "flow",
    },

    "m12": {
        "title": "🚀 Módulo 12 — Aplicación Avanzada Apex Quant",
        "text": (
            "En el nivel avanzado se combinan los conceptos estudiados para "
            "construir un proceso de análisis más completo.\n\n"
            "🚀 Áreas de aplicación:\n"
            "• Análisis Multi-Timeframe.\n"
            "• Contexto + estructura + liquidez.\n"
            "• BOS/CHOCH + OB/FVG.\n"
            "• Sesiones de Londres y Nueva York.\n"
            "• Volumen y volatilidad.\n"
            "• Calendario económico.\n"
            "• Backtesting.\n"
            "• Diario de trading.\n"
            "• Estadísticas de una metodología.\n"
            "• Construcción y revisión de un plan operativo.\n\n"

            "📊 Instrumentos de referencia dentro del ecosistema Apex Quant:\n"
            "GBP/USD, GBP/JPY, US30 y XAU/USD, aplicando especial cautela "
            "a instrumentos con elevada volatilidad.\n\n"

            "El objetivo de este módulo es aprender a integrar información y "
            "tomar decisiones mediante un proceso definido, no buscar una señal "
            "infalible."
        ),
        "visual": "mtf",
    },
}

def academy_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📘 Fundamentos",
                callback_data="academy_m1"
            ),
            InlineKeyboardButton(
                "📊 Técnico",
                callback_data="academy_m2"
            )
        ],
        [
            InlineKeyboardButton(
                "📰 Fundamental",
                callback_data="academy_m3"
            ),
            InlineKeyboardButton(
                "🏦 Institucional",
                callback_data="academy_m4"
            )
        ],
        [
            InlineKeyboardButton(
                "🧩 Estructura",
                callback_data="academy_m5"
            ),
            InlineKeyboardButton(
                "💧 Liquidez",
                callback_data="academy_m6"
            )
        ],
        [
            InlineKeyboardButton(
                "🟦 OB / FVG",
                callback_data="academy_m7"
            ),
            InlineKeyboardButton(
                "⏱️ Estilos",
                callback_data="academy_m8"
            )
        ],
        [
            InlineKeyboardButton(
                "🛡️ Riesgo",
                callback_data="academy_m9"
            ),
            InlineKeyboardButton(
                "🧠 Psicología",
                callback_data="academy_m10"
            )
        ],
        [
            InlineKeyboardButton(
                "🔬 Construir análisis",
                callback_data="academy_m11"
            )
        ],
        [
            InlineKeyboardButton(
                "🚀 Aplicación Avanzada",
                callback_data="academy_m12"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ],
    ])

async def show_academy(query):
    text = (
        "🎓 <b>ACADEMIA APEX QUANT</b>\n\n"
        "📚 Ruta educativa de trading desde los fundamentos "
        "hasta la aplicación avanzada.\n\n"
        
        "Aprende progresivamente:\n"
        "📘 Fundamentos\n"
        "📊 Análisis Técnico\n"
        "📰 Análisis Fundamental\n"
        "🏦 Análisis Institucional\n"
        "🧩 Estructura de Mercado\n"
        "💧 Liquidez\n"
        "🟦 Order Blocks y FVG\n"
        "⏱️ Estilos de Trading\n"
        "🛡️ Gestión de Riesgo\n"
        "🧠 Psicología y Disciplina\n"
        "🔬 Construcción de Análisis\n"
        "🚀 Aplicación Avanzada\n\n"
        
        "📖 <b>12 módulos educativos</b>\n\n"
        
        "Selecciona un módulo para comenzar o continuar tu aprendizaje.\n\n"
        
        "⚠️ <b>Importante:</b> el contenido de esta Academia tiene "
        "finalidad exclusivamente educativa. El aprendizaje de una "
        "metodología no garantiza resultados futuros en los mercados."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=academy_menu()
    )

async def show_academy_module(query, module_id):
    module = ACADEMY_MODULES.get(module_id)
    if not module:
        await show_academy(query)
        return
    keyboard = []
    if module.get("visual"):
        keyboard.append([InlineKeyboardButton("🖼️ Ver material visual", callback_data=f"academy_visual_{module['visual']}")])
    keyboard.extend([
        [InlineKeyboardButton("🎓 Academia", callback_data="academy")],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back_main")],
    ])
    text = (
        f"{module['title']}\n\n"
        f"{module['text']}\n\n"
        "⚠️ <b>Contenido educativo:</b> estudiar un concepto no garantiza que una operación futura tenga un resultado determinado."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_academy_visual(query, kind):
    """Genera y envía el material visual oficial de academy_visuals.py."""

    builder = ACADEMY_VISUAL_BUILDERS.get(kind)
    caption = ACADEMY_VISUAL_CAPTIONS.get(kind)

    if builder is None or caption is None:
        await query.answer("Material visual no disponible.", show_alert=True)
        return

    fig = None

    try:
        fig = builder()
        image = io.BytesIO()
        fig.savefig(
            image,
            format="png",
            dpi=100,
            facecolor=fig.get_facecolor(),
            bbox_inches=None
        )
        image.seek(0)
        image.name = f"apex_quant_{kind}.png"

        await query.message.reply_photo(
            photo=image,
            caption=caption
        )
        await query.answer("Material visual enviado.")

    except Exception as error:
        logger.exception("Error generando material visual %s: %s", kind, error)
        await query.answer(
            "No se pudo generar el material visual.",
            show_alert=True
        )

    finally:
        if fig is not None:
            plt.close(fig)


# ============================================================
# BILLETERA / RETIROS
# ============================================================

async def show_wallet(query):
    balance = get_wallet_balance(query.from_user.id)
    text = (
        "💰 <b>BILLETERA APEX QUANT</b>\n\n"
        f"💵 Saldo disponible: <b>{balance:.2f} USDT</b>\n"
        "🌐 Red de retiros: <b>BNB Smart Chain / BEP20</b>\n"
        f"📉 Retiro mínimo: <b>{WITHDRAWAL_MIN_USDT:.0f} USDT</b>\n"
        "💸 Comisión de retiro: <b>0%</b>\n\n"
        "Los saldos provienen de comisiones registradas en el programa de referidos."
    )
    keyboard = [
        [InlineKeyboardButton("💸 Solicitar retiro", callback_data="withdraw_info")],
        [InlineKeyboardButton("📜 Historial", callback_data="withdraw_history")],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def withdraw_info(query):
    text = (
        "💸 <b>SOLICITAR RETIRO</b>\n\n"
        f"📉 Mínimo: <b>{WITHDRAWAL_MIN_USDT:.0f} USDT</b>\n"
        "💸 Comisión: <b>0%</b>\n"
        "🌐 Red: <b>BNB Smart Chain / BEP20</b>\n\n"
        "Usa:\n"
        "<code>/withdraw DIRECCION_BEP20 IMPORTE</code>\n\n"
        "Ejemplo:\n"
        "<code>/withdraw 0x... 25</code>\n\n"
        "⚠️ Comprueba que la dirección sea tuya y que soporte BNB Smart Chain. Nunca compartas una clave privada."
    )
    keyboard = [[InlineKeyboardButton("💰 Billetera", callback_data="wallet")], [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def withdraw_history(query):
    withdrawals = load_withdrawals()
    user_items = [v for v in withdrawals.values() if str(v.get("user_id")) == str(query.from_user.id)]
    user_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    text = "💸 <b>HISTORIAL DE RETIROS</b>\n\n"
    if not user_items:
        text += "📭 No tienes retiros registrados."
    else:
        for item in user_items[:10]:
            text += (
                f"• <b>{item.get('amount', '0')} USDT</b> — {item.get('status', 'pending')}\n"
                f"  📅 {item.get('created_at', 'N/D')}\n"
                f"  🔗 <code>{escape(str(item.get('tx_hash', 'Pendiente')))}</code>\n"
            )
    keyboard = [[InlineKeyboardButton("💰 Billetera", callback_data="wallet")], [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


def valid_bep20_address(address):
    return isinstance(address, str) and len(address) == 42 and address.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in address[2:])


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if len(context.args) != 2:
        await update.message.reply_text("💸 <b>RETIRO</b>\n\nUsa:\n<code>/withdraw DIRECCION_BEP20 IMPORTE</code>", parse_mode="HTML")
        return
    address = context.args[0].strip()
    if not valid_bep20_address(address):
        await update.message.reply_text("⚠️ La dirección BEP20 no tiene un formato válido.")
        return
    amount = _safe_decimal(context.args[1])
    balance = get_wallet_balance(user.id)
    if amount < WITHDRAWAL_MIN_USDT:
        await update.message.reply_text(f"⚠️ El retiro mínimo es de {WITHDRAWAL_MIN_USDT:.0f} USDT.")
        return
    if amount > balance:
        await update.message.reply_text(f"⚠️ Saldo insuficiente. Disponible: {balance:.2f} USDT.")
        return

    withdrawals = load_withdrawals()
    withdrawal_id = f"wd_{user.id}_{int(datetime.now().timestamp())}"
    entry = {
        "id": withdrawal_id,
        "user_id": str(user.id),
        "address": address,
        "amount": str(amount),
        "fee": "0",
        "network": "BNB Smart Chain / BEP20",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    # Se reserva el saldo antes de intentar el procesamiento automático.
    if not debit_wallet(user.id, amount, "Retiro solicitado", withdrawal_id):
        await update.message.reply_text("❌ No se pudo reservar el saldo del retiro.")
        return
    withdrawals[withdrawal_id] = entry
    save_withdrawals(withdrawals)

    if AUTO_WITHDRAWALS_ENABLED:
        try:
            result = await asyncio.to_thread(execute_auto_withdrawal, entry)
            withdrawals = load_withdrawals()
            withdrawals[withdrawal_id] = result
            save_withdrawals(withdrawals)
            if result.get("status") == "completed":
                await update.message.reply_text(
                    "✅ <b>RETIRO ENVIADO</b>\n\n"
                    f"💰 Importe: <b>{amount:.2f} USDT</b>\n"
                    f"🔗 TXID: <code>{escape(result.get('tx_hash', ''))}</code>",
                    parse_mode="HTML"
                )
                return
            # Si el envío automático no pudo completarse, se devuelve el saldo reservado.
            credit_wallet(user.id, amount, "Reintegro de retiro pendiente", withdrawal_id)
            result["status"] = "cancelled"
            result["refunded_at"] = datetime.now().isoformat()
            withdrawals[withdrawal_id] = result
            save_withdrawals(withdrawals)
        except Exception as error:
            logger.error("Error en retiro automático: %s", error)
            credit_wallet(user.id, amount, "Reintegro por error de retiro", withdrawal_id)
            withdrawals = load_withdrawals()
            withdrawals[withdrawal_id]["status"] = "cancelled"
            withdrawals[withdrawal_id]["error"] = str(error)
            withdrawals[withdrawal_id]["refunded_at"] = datetime.now().isoformat()
            save_withdrawals(withdrawals)

    await update.message.reply_text(
        "✅ <b>SOLICITUD DE RETIRO REGISTRADA</b>\n\n"
        f"💰 Importe: <b>{amount:.2f} USDT</b>\n"
        f"📍 Dirección: <code>{escape(address)}</code>\n"
        "🌐 Red: <b>BNB Smart Chain / BEP20</b>\n"
        "💸 Comisión: <b>0%</b>\n\n"
        "Estado: <b>PENDIENTE</b>",
        parse_mode="HTML"
    )


def execute_auto_withdrawal(entry):
    """Envía USDT solo cuando AUTO_WITHDRAWALS_ENABLED está activo.

    Requiere web3 instalado en requirements.txt. Si no está disponible,
    la solicitud permanece pendiente y el bot no pierde el saldo reservado.
    """
    if not AUTO_WITHDRAWALS_ENABLED:
        return {**entry, "status": "pending"}
    if not WITHDRAWAL_PRIVATE_KEY:
        return {**entry, "status": "pending", "error": "WITHDRAWAL_PRIVATE_KEY no configurada"}
    try:
        from web3 import Web3
    except ImportError:
        return {**entry, "status": "pending", "error": "web3 no instalado"}

    # Construcción y firma del envío USDT BEP20.
    web3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
    if not web3.is_connected():
        return {**entry, "status": "pending", "error": "No hay conexión RPC"}
    account = web3.eth.account.from_key(WITHDRAWAL_PRIVATE_KEY)
    abi = [{
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    }]
    contract = web3.eth.contract(address=Web3.to_checksum_address(USDT_CONTRACT_ADDRESS), abi=abi)
    value = int((_safe_decimal(entry["amount"]) * (Decimal(10) ** USDT_DECIMALS)).to_integral_value())
    nonce = web3.eth.get_transaction_count(account.address)
    tx = contract.functions.transfer(
        Web3.to_checksum_address(entry["address"]),
        value,
    ).build_transaction({
        "chainId": BSC_CHAIN_ID,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": web3.eth.gas_price,
    })
    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    return {**entry, "status": "completed", "tx_hash": web3.to_hex(tx_hash), "processed_at": datetime.now().isoformat()}


# ============================================================
# ADMINISTRACIÓN
# ============================================================

async def admin_menu(query):

    if not is_admin(
        query.from_user.id
    ):

        await query.edit_message_text(
            "⛔ <b>Acceso restringido.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="back_main"
                    )
                ]
            ])
        )

        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📡 Enviar señal",
                callback_data="admin_send_signal"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Historial de señales",
                callback_data="admin_signal_history"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Suscriptores activos",
                callback_data="admin_subscribers"
            )
        ],
        [
            InlineKeyboardButton(
                "📈 Estadísticas",
                callback_data="admin_statistics"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Pagos",
                callback_data="admin_payments"
            ),
            InlineKeyboardButton(
                "💸 Retiros",
                callback_data="admin_withdrawals"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="back_main"
            )
        ]
    ]

    text = (
        "🛠️ <b>ADMINISTRACIÓN APEX QUANT</b>\n\n"
        "Desde aquí puedes gestionar el servicio "
        "de señales y consultar información "
        "de los suscriptores."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


async def show_admin_menu(query):

    await admin_menu(query)


# ============================================================
# ADMIN - ENVIAR SEÑAL
# ============================================================

async def admin_send_signal(query):

    if not is_admin(
        query.from_user.id
    ):
        return

    text = (
        "📡 <b>ENVIAR SEÑAL</b>\n\n"
        "Para enviar una señal utiliza el comando:\n\n"
        "<code>/signal TEXTO_DE_LA_SEÑAL</code>\n\n"
        "Ejemplo:\n"
        "<code>/signal\n"
        "📊 EUR/USD\n"
        "🟢 BUY\n"
        "🎯 Entrada: 1.1700\n"
        "🛑 SL: 1.1680\n"
        "💰 TP: 1.1760</code>\n\n"
        "La señal será enviada a los usuarios "
        "con una suscripción activa."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="admin_menu"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# ADMIN - HISTORIAL DE SEÑALES
# ============================================================

async def admin_signal_history(query):

    if not is_admin(
        query.from_user.id
    ):
        return

    text = (
        "📊 <b>HISTORIAL DE SEÑALES</b>\n\n"
        "El historial de señales estará disponible "
        "cuando existan señales registradas.\n\n"
        "📌 Las señales enviadas mediante "
        "<code>/signal</code> pueden registrarse "
        "en el historial."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="admin_menu"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# ADMIN - SUSCRIPTORES
# ============================================================

async def admin_subscribers(query):

    if not is_admin(
        query.from_user.id
    ):
        return

    subscriptions = load_subscriptions()

    active_users = []

    for user_id, data in subscriptions.items():

        if data.get("active", False):

            try:

                expiration = datetime.fromisoformat(
                    data.get("expires_at", "")
                )

                if datetime.now() < expiration:
                    active_users.append(
                        user_id
                    )

            except Exception:
                continue

    text = (
        "👥 <b>SUSCRIPTORES ACTIVOS</b>\n\n"
        f"🟢 Total activos: "
        f"<b>{len(active_users)}</b>\n\n"
    )

    if active_users:

        text += (
            "🆔 Usuarios:\n"
            + "\n".join(
                f"• <code>{uid}</code>"
                for uid in active_users[:50]
            )
        )

    else:

        text += (
            "📭 No hay suscriptores activos."
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data="admin_subscribers"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="admin_menu"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# ADMIN - ESTADÍSTICAS
# ============================================================

async def admin_statistics(query):

    if not is_admin(
        query.from_user.id
    ):
        return

    subscriptions = load_subscriptions()
    referrals = load_referrals()

    total_subscriptions = len(
        subscriptions
    )

    active_subscriptions = 0

    for user_id in subscriptions:

        if is_subscription_active(
            user_id
        ):
            active_subscriptions += 1

    total_referral_users = len(
        referrals
    )

    text = (
        "📈 <b>ESTADÍSTICAS APEX QUANT</b>\n\n"
        f"📡 Suscripciones registradas: "
        f"<b>{total_subscriptions}</b>\n"
        f"🟢 Suscripciones activas: "
        f"<b>{active_subscriptions}</b>\n"
        f"👥 Usuarios en estructura de referidos: "
        f"<b>{total_referral_users}</b>\n\n"
        "💰 Precio de señales: "
        f"<b>{SIGNALS_PRICE_USDT} USDT / 30 días</b>\n"
        f"💳 Pagos verificados: <b>{len(load_payments())}</b>\n"
        f"💸 Retiros registrados: <b>{len(load_withdrawals())}</b>"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data="admin_statistics"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="admin_menu"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )

# ============================================================
# ADMIN - PAGOS Y RETIROS
# ============================================================

async def admin_payments(query):
    if not is_admin(query.from_user.id):
        return
    payments = load_payments()
    credited = [v for v in payments.values() if v.get("status") == "credited"]
    total = sum((_safe_decimal(v.get("amount")) for v in credited), Decimal("0"))
    text = (
        "💳 <b>PAGOS VERIFICADOS</b>\n\n"
        f"🧾 Transacciones procesadas: <b>{len(credited)}</b>\n"
        f"💰 Volumen registrado: <b>{total:.2f} USDT</b>\n\n"
        "La verificación comprueba token, contrato, wallet receptora, importe y confirmaciones."
    )
    keyboard = [[InlineKeyboardButton("🔄 Actualizar", callback_data="admin_payments")], [InlineKeyboardButton("🔙 Volver", callback_data="admin_menu")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_withdrawals(query):
    if not is_admin(query.from_user.id):
        return
    withdrawals = load_withdrawals()
    pending = [v for v in withdrawals.values() if v.get("status") == "pending"]
    total_pending = sum((_safe_decimal(v.get("amount")) for v in pending), Decimal("0"))
    text = (
        "💸 <b>RETIROS</b>\n\n"
        f"⏳ Pendientes: <b>{len(pending)}</b>\n"
        f"💰 Total pendiente: <b>{total_pending:.2f} USDT</b>\n\n"
        f"⚙️ Automáticos: <b>{'ACTIVOS' if AUTO_WITHDRAWALS_ENABLED else 'DESACTIVADOS'}</b>"
    )
    keyboard = [[InlineKeyboardButton("🔄 Actualizar", callback_data="admin_withdrawals")], [InlineKeyboardButton("🔙 Volver", callback_data="admin_menu")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


# ============================================================
# COMANDO /START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user:
        return

    user_id = user.id

    # --------------------------------------------------------
    # PROCESAR REFERIDO
    # --------------------------------------------------------

    if context.args:

        referral_code = context.args[0]

        if referral_code.startswith("ref_"):

            referred_by = referral_code.replace(
                "ref_",
                "",
                1
            )

            if referred_by.isdigit():

                if str(user_id) != str(referred_by):

                    register_referral(
                        user_id,
                        referred_by
                    )

    # --------------------------------------------------------
    # PROCESAR NIVELES
    # --------------------------------------------------------

    try:
        process_referral_levels(user_id)
    except Exception as error:
        logger.error(
            "Error procesando niveles de referido: %s",
            error
        )

    # --------------------------------------------------------
    # MENSAJE DE BIENVENIDA
    # --------------------------------------------------------

    text = (
        "🔥 <b>Bienvenido a Apex Quant</b>\n\n"
        "Centro de información y herramientas "
        "para mercados financieros.\n\n"
        "📊 <b>Mercados</b>\n"
        "Consulta el calendario económico y "
        "eventos relevantes.\n\n"
        "📡 <b>Señales</b>\n"
        "Accede al servicio de señales de "
        "Apex Quant mediante suscripción.\n\n"
        "📋 <b>CopyTrading</b>\n"
        "Accede al servicio de CopyTrading "
        "de Apex Quant a través de OneRoyal.\n\n"
        "👥 <b>Referidos</b>\n"
        "Comparte Apex Quant y consulta tu "
        "estructura de referidos.\n\n"
        "🎓 <b>Academia</b>\n"
        "Aprende trading desde los fundamentos hasta conceptos avanzados.\n\n"
        "💰 <b>Billetera</b>\n"
        "Consulta tus comisiones y solicita retiros.\n\n"
        "⚠️ <b>Aviso de riesgo:</b>\n"
        "El análisis, las señales y las herramientas "
        "de Apex Quant no garantizan resultados. "
        "Los mercados financieros implican riesgo "
        "de pérdida de capital."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(user_id)
    )


# ============================================================
# COMANDO /SIGNAL
# ============================================================

async def signal_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(user.id):

        await update.message.reply_text(
            "⛔ <b>Acceso restringido.</b>\n\n"
            "Este comando solo está disponible "
            "para el administrador.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # OBTENER TEXTO DE LA SEÑAL
    # --------------------------------------------------------

    message_text = update.message.text or ""

    parts = message_text.split(
        " ",
        1
    )

    if len(parts) < 2:

        await update.message.reply_text(
            "📡 <b>FORMATO DE SEÑAL</b>\n\n"
            "Utiliza:\n\n"
            "<code>/signal TEXTO DE LA SEÑAL</code>\n\n"
            "Ejemplo:\n"
            "<code>/signal\n"
            "📊 EUR/USD\n"
            "🟢 BUY\n"
            "🎯 Entrada: 1.1700\n"
            "🛑 SL: 1.1680\n"
            "💰 TP: 1.1760</code>",
            parse_mode="HTML"
        )

        return

    signal_text = parts[1].strip()
    safe_signal_text = escape(signal_text)

    # --------------------------------------------------------
    # CARGAR SUSCRIPTORES
    # --------------------------------------------------------

    subscriptions = load_subscriptions()

    sent_count = 0
    failed_count = 0

    signal_message = (
        "📡 <b>APEX QUANT — NUEVA SEÑAL</b>\n\n"
        f"{safe_signal_text}\n\n"
        "⚠️ Esta información no garantiza "
        "resultados financieros.\n"
        "Opera siempre de acuerdo con tu "
        "gestión de riesgo."
    )

    # --------------------------------------------------------
    # ENVIAR A SUSCRIPTORES ACTIVOS
    # --------------------------------------------------------

    for user_id in subscriptions:

        if not is_subscription_active(user_id):
            continue

        try:

            await context.bot.send_message(
                chat_id=int(user_id),
                text=signal_message,
                parse_mode="HTML"
            )

            sent_count += 1

        except Exception as error:

            failed_count += 1

            logger.error(
                "Error enviando señal a %s: %s",
                user_id,
                error
            )

    # --------------------------------------------------------
    # RESULTADO AL ADMIN
    # --------------------------------------------------------

    await update.message.reply_text(
        "✅ <b>SEÑAL PROCESADA</b>\n\n"
        f"📡 Enviadas: <b>{sent_count}</b>\n"
        f"⚠️ Fallidas: <b>{failed_count}</b>",
        parse_mode="HTML"
    )


# ============================================================
# COMANDO /ACTIVATE
# ============================================================

async def activate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(user.id):

        await update.message.reply_text(
            "⛔ <b>Acceso restringido.</b>",
            parse_mode="HTML"
        )

        return

    if not context.args:

        await update.message.reply_text(
            "📡 <b>ACTIVAR SUSCRIPCIÓN</b>\n\n"
            "Utiliza:\n\n"
            "<code>/activate ID_TELEGRAM</code>\n\n"
            "Ejemplo:\n"
            "<code>/activate 123456789</code>",
            parse_mode="HTML"
        )

        return

    target_id = context.args[0]

    if not target_id.isdigit():

        await update.message.reply_text(
            "⚠️ El ID de Telegram debe ser numérico.",
            parse_mode="HTML"
        )

        return

    expiration = (
        datetime.now()
        + timedelta(
            days=SIGNALS_DURATION_DAYS
        )
    )

    subscriptions = load_subscriptions()

    subscriptions[str(target_id)] = {
        "active": True,
        "activated_at": datetime.now().isoformat(),
        "expires_at": expiration.isoformat(),
        "duration_days": SIGNALS_DURATION_DAYS,
        "price_usdt": SIGNALS_PRICE_USDT
    }

    if not save_subscriptions(
        subscriptions
    ):

        await update.message.reply_text(
            "❌ No se pudo guardar la suscripción.",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # AVISAR AL USUARIO
    # --------------------------------------------------------

    try:

        await context.bot.send_message(
            chat_id=int(target_id),
            text=(
                "🎉 <b>¡SUSCRIPCIÓN ACTIVADA!</b>\n\n"
                "📡 Tu suscripción a las señales "
                "de Apex Quant está activa.\n\n"
                f"📆 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
                f"📅 Vencimiento: <b>{expiration.strftime('%Y-%m-%d %H:%M')}</b>\n\n"
                "A partir de ahora recibirás las "
                "señales mientras tu suscripción "
                "permanezca activa.\n\n"
                "⚠️ Las señales no garantizan resultados."
            ),
            parse_mode="HTML"
        )

    except Exception as error:

        logger.error(
            "No se pudo avisar al usuario activado: %s",
            error
        )

    await update.message.reply_text(
        "✅ <b>SUSCRIPCIÓN ACTIVADA</b>\n\n"
        f"🆔 Usuario: <code>{target_id}</code>\n"
        f"📆 Vencimiento: "
        f"<b>{expiration.strftime('%Y-%m-%d %H:%M')}</b>",
        parse_mode="HTML"
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data

    try:

        # ====================================================
        # MENÚ PRINCIPAL
        # ====================================================

        if data == "back_main":

            await query.edit_message_text(
                "🔥 <b>APEX QUANT</b>\n\n"
                "Selecciona una opción:",
                parse_mode="HTML",
                reply_markup=main_menu(
                    query.from_user.id
                )
            )

            return

        # ====================================================
        # BROKER ONEROYAL
        # ====================================================

        if data == "broker_oneroyal":

            await show_broker_oneroyal(query)
            return

        # ====================================================
        # MERCADOS
        # ====================================================

        if data == "markets":

            await show_markets(query)
            return

        # ====================================================
        # CALENDARIO
        # ====================================================

        if data == "calendar":

            await show_calendar(query)
            return

        if data == "calendar_today":

            await show_calendar_today(query)
            return

        if data == "calendar_tomorrow":

            await show_calendar_tomorrow(query)
            return

        if data == "calendar_week":

            await show_calendar_week(query)
            return

        if data == "calendar_high":

            await show_calendar_high(query)
            return

        if data == "calendar_currency":

            await currency_events(query)
            return

        # ====================================================
        # DIVISAS
        # ====================================================

        if data.startswith("currency_"):

            currency = data.replace(
                "currency_",
                "",
                1
            )

            await show_currency_events(
                query,
                currency
            )

            return

        # ====================================================
        # COPYTRADING
        # ====================================================

        if data == "copytrading":

            await show_copy_menu(query)
            return

        if data == "copy_info":

            await show_copy_info(query)
            return

        if data == "copy_follow":

            await show_copy_follow(query)
            return

        if data == "copy_register":

            await show_copy_register(query)
            return

        if data == "copy_steps":

            await show_copy_steps(query)
            return

        if data == "copy_link_missing":

            await show_missing_copy_link(query)
            return

        if data == "ib_link_missing":

            await show_missing_ib_link(query)
            return

        # ====================================================
        # SEÑALES
        # ====================================================

        if data == "signals":

            await show_signals(query)
            return

        if data == "signals_info":

            await signals_info(query)
            return

        if data == "signals_subscribe":

            await signals_subscribe(query)
            return

        if data == "signals_status":

            await signals_status(query)
            return

        if data == "signals_terms":

            await signals_terms(query)
            return

        # ====================================================
        # REFERIDOS
        # ====================================================

        if data == "referrals":

            await show_referrals(query)
            return

        if data == "referral_link":

            await show_referral_link(query)
            return

        if data == "referral_stats":

            await show_referral_stats(query)
            return

        if data == "referral_commissions":

            await show_referral_commissions(query)
            return

        # ====================================================
        # IDIOMA
        # ====================================================

        if data == "language":

            await show_language(query)
            return

        if data == "language_es":

            await set_language(
                query,
                "es"
            )

            return

        if data == "language_en":

            await set_language(
                query,
                "en"
            )

            return

        # ====================================================
        # CONFIGURACIÓN
        # ====================================================

        if data == "settings":

            await show_settings(query)
            return

        # ====================================================
        # ACADEMIA
        # ====================================================

        if data == "academy":
            await show_academy(query)
            return

        if data.startswith("academy_m"):
            await show_academy_module(query, data.replace("academy_", "", 1))
            return

        if data.startswith("academy_visual_"):
            await show_academy_visual(query, data.replace("academy_visual_", "", 1))
            return

        # ====================================================
        # BILLETERA / PAGOS
        # ====================================================

        if data == "wallet":
            await show_wallet(query)
            return

        if data == "withdraw_info":
            await withdraw_info(query)
            return

        if data == "withdraw_history":
            await withdraw_history(query)
            return

        if data == "payment_verify":
            await payment_verify_info(query)
            return

        # ====================================================
        # ADMINISTRACIÓN
        # ====================================================

        if data == "admin_menu":

            await show_admin_menu(query)
            return

        if data == "admin_send_signal":

            await admin_send_signal(query)
            return

        if data == "admin_signal_history":

            await admin_signal_history(query)
            return

        if data == "admin_subscribers":

            await admin_subscribers(query)
            return

        if data == "admin_statistics":

            await admin_statistics(query)
            return

        if data == "admin_payments":

            await admin_payments(query)
            return

        if data == "admin_withdrawals":

            await admin_withdrawals(query)
            return

        # ====================================================
        # CALLBACK NO RECONOCIDO
        # ====================================================

        await query.edit_message_text(
            "⚠️ <b>Opción no disponible.</b>\n\n"
            "Regresa al menú principal.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 Menú principal",
                        callback_data="back_main"
                    )
                ]
            ])
        )

    except Exception as error:

        logger.error(
            "Error en button_handler: %s",
            error,
            exc_info=True
        )

        try:

            await query.edit_message_text(
                "⚠️ <b>Se produjo un error.</b>\n\n"
                "Intenta nuevamente desde el menú principal.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🏠 Menú principal",
                            callback_data="back_main"
                        )
                    ]
                ])
            )

        except Exception:

            pass


# ============================================================
# MANEJADOR DE ERRORES
# ============================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "Exception while handling an update:",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "❌ BOT_TOKEN no está configurado."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # --------------------------------------------------------
    # COMANDOS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "signal",
            signal_command
        )
    )

    application.add_handler(
        CommandHandler(
            "activate",
            activate_command
        )
    )

    application.add_handler(
        CommandHandler(
            "verify",
            verify_payment_command
        )
    )

    application.add_handler(
        CommandHandler(
            "withdraw",
            withdraw_command
        )
    )

    # --------------------------------------------------------
    # BOTONES
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # --------------------------------------------------------
    # ERRORES
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    # --------------------------------------------------------
    # INICIAR BOT
    # --------------------------------------------------------

    logger.info(
        "🔥 Apex Quant Bot iniciado correctamente."
    )

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":
    main()
