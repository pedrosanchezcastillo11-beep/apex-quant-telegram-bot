# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime, timedelta, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ============================================================
# ADMINISTRACIÓN
# ============================================================

async def show_admin_menu(query):
    user = query.from_user

    if not user or not is_admin(user.id):
        await query.edit_message_text(
            "⛔ No tienes permiso para acceder a esta sección.",
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )
        return

    text = (
        "🛠️ *Administración Apex Quant*\n\n"
        "Selecciona una opción:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📡 Enviar señal",
                callback_data="admin_send_signal",
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Historial de señales",
                callback_data="admin_signal_history",
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Suscriptores activos",
                callback_data="admin_active_users",
            )
        ],
        [
            InlineKeyboardButton(
                "📈 Estadísticas",
                callback_data="admin_statistics",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Menú principal",
                callback_data="main_menu",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# CONFIGURACIÓN
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Falta la variable de entorno BOT_TOKEN")


# ============================================================
# REFERIDOS — ALMACENAMIENTO
# ============================================================

REFERRALS_FILE = os.getenv(
    "REFERRALS_FILE",
    "referrals.json"
)


# ============================================================
# SEÑALES — SUSCRIPCIONES
# ============================================================

SUBSCRIPTIONS_FILE = os.getenv(
    "SUBSCRIPTIONS_FILE",
    "subscriptions.json"
)

SIGNALS_PRICE_USDT = 30
SIGNALS_DURATION_DAYS = 30

USDT_BEP20_ADDRESS = os.getenv(
    "USDT_BEP20_ADDRESS",
    ""
)

ADMIN_TELEGRAM_ID = os.getenv(
    "ADMIN_TELEGRAM_ID",
    ""
)


def load_referrals():
    """Carga los datos de referidos desde el archivo JSON."""

    try:
        if not os.path.exists(REFERRALS_FILE):
            return {
                "users": {},
                "referrals": {}
            }

        with open(
            REFERRALS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(
                "Formato de referidos inválido"
            )

        data.setdefault("users", {})
        data.setdefault("referrals", {})

        return data

    except Exception as error:

        logger.error(
            "Error cargando referidos: %s",
            error
        )

        try:

            if os.path.exists(
                REFERRALS_FILE
            ):

                backup = (
                    f"{REFERRALS_FILE}.corrupt"
                )

                os.replace(
                    REFERRALS_FILE,
                    backup
                )

                logger.error(
                    "Archivo dañado respaldado en %s",
                    backup
                )

        except Exception as backup_error:

            logger.error(
                "No se pudo respaldar: %s",
                backup_error
            )

        return {
            "users": {},
            "referrals": {}
        }


def save_referrals(data):
    """Guarda los datos de referidos en el archivo JSON."""

    try:

        temp_file = (
            f"{REFERRALS_FILE}.tmp"
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
            REFERRALS_FILE
        )

    except Exception as error:

        logger.error(
            "Error guardando referidos: %s",
            error
        )


def register_user(user):
    """Registra un usuario mediante su Telegram ID."""

    if not user:
        return

    data = load_referrals()

    user_id = str(user.id)

    if user_id not in data["users"]:

        data["users"][user_id] = {
            "telegram_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "referred_by": None
        }

        data["referrals"].setdefault(
            user_id,
            []
        )

    else:

        data["users"][user_id]["username"] = (
            user.username or ""
        )

        data["users"][user_id]["first_name"] = (
            user.first_name or ""
        )

        data["referrals"].setdefault(
            user_id,
            []
        )

    save_referrals(data)

    return data


def process_referral(
    user,
    start_parameter
):
    """
    Procesa un enlace:

    /start ref_123456789

    El usuario conserva siempre su referente
    original.
    """

    if not user or not start_parameter:
        return False

    parameter = str(
        start_parameter
    ).strip()

    if not parameter.startswith(
        "ref_"
    ):
        return False

    referrer_id = (
        parameter[4:]
        .strip()
    )

    if not referrer_id.isdigit():

        logger.warning(
            "Código de referido inválido: %s",
            parameter
        )

        return False

    user_id = str(user.id)

    # ========================================================
    # BLOQUEAR AUTO-REFERENCIA
    # ========================================================

    if referrer_id == user_id:

        logger.info(
            "Auto-referencia bloqueada para Telegram ID %s",
            user_id
        )

        return False

    data = load_referrals()

    # ========================================================
    # REGISTRAR USUARIO
    # ========================================================

    if user_id not in data["users"]:

        data["users"][user_id] = {
            "telegram_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "referred_by": None
        }

    else:

        data["users"][user_id]["username"] = (
            user.username or ""
        )

        data["users"][user_id]["first_name"] = (
            user.first_name or ""
        )

    data["referrals"].setdefault(
        user_id,
        []
    )

    # ========================================================
    # CREAR REFERENTE SI NO EXISTE
    # ========================================================

    if referrer_id not in data["users"]:

        logger.warning(
            "Referente %s no estaba registrado. "
            "Se crea registro básico.",
            referrer_id
        )

        data["users"][referrer_id] = {
            "telegram_id": int(
                referrer_id
            ),
            "username": "",
            "first_name": "",
            "referred_by": None
        }

    # ========================================================
    # UNA CUENTA SOLO PUEDE TENER UN REFERENTE
    # ========================================================

    if data["users"][user_id].get(
        "referred_by"
    ):

        logger.info(
            "Usuario %s ya tiene referente %s. "
            "No se cambia.",
            user_id,
            data["users"][user_id][
                "referred_by"
            ]
        )

        save_referrals(data)

        return False

    # ========================================================
    # EVITAR DUPLICADOS
    # ========================================================

    data["referrals"].setdefault(
        referrer_id,
        []
    )

    if user_id in data["referrals"][
        referrer_id
    ]:

        logger.info(
            "Usuario %s ya está registrado "
            "como referido de %s.",
            user_id,
            referrer_id
        )

        data["users"][user_id][
            "referred_by"
        ] = referrer_id

        save_referrals(data)

        return False

    # ========================================================
    # REGISTRAR NUEVO REFERIDO
    # ========================================================

    data["referrals"][
        referrer_id
    ].append(user_id)

    data["users"][user_id][
        "referred_by"
    ] = referrer_id

    save_referrals(data)

    logger.info(
        "Nuevo referido registrado: %s -> %s",
        referrer_id,
        user_id
    )

    return True


def get_referral_levels(user_id):
    """
    Devuelve los referidos de:

    Nivel 1 = referidos directos
    Nivel 2 = referidos de Nivel 1
    Nivel 3 = referidos de Nivel 2
    """

    data = load_referrals()

    root_id = str(user_id)

    # ========================================================
    # NIVEL 1
    # ========================================================

    level_1 = list(
        data["referrals"].get(
            root_id,
            []
        )
    )

    # ========================================================
    # NIVEL 2
    # ========================================================

    level_2 = []

    for user_l1 in level_1:

        level_2.extend(
            data["referrals"].get(
                str(user_l1),
                []
            )
        )

    # ========================================================
    # NIVEL 3
    # ========================================================

    level_3 = []

    for user_l2 in level_2:

        level_3.extend(
            data["referrals"].get(
                str(user_l2),
                []
            )
        )

    return {
        "level_1": level_1,
        "level_2": level_2,
        "level_3": level_3,
    }


def get_referral_count(user_id):
    """
    Devuelve el número de referidos directos
    de un usuario.
    """

    return len(
        get_referral_levels(
            user_id
        )["level_1"]
    )


FINANCE_CALENDAR_BASE = (
    "https://www.financecalendar.com/wp-json/fc/v1"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO,
)

logging.getLogger(
    "httpx"
).setLevel(
    logging.WARNING
)

logger = logging.getLogger(
    "apex_quant"
)


# ============================================================
# TECLADO PRINCIPAL
# ============================================================

def main_menu(user_id=None):

    keyboard = [

        [
            InlineKeyboardButton(
                "📊 Mercados",
                callback_data="markets",
            ),

            InlineKeyboardButton(
                "📡 Señales",
                callback_data="signals",
            ),
        ],

       [
            InlineKeyboardButton(
                "📋 CopyTrading",
                callback_data="copytrading",
            ),

            InlineKeyboardButton(
                "👥 Referidos",
                callback_data="referrals",
            ),
        ],

        [
            InlineKeyboardButton(
                "💎 Fondeo",
                callback_data="funding_menu",
            ),
        ],
    

        [
            InlineKeyboardButton(
                "💎 Fondeo",
                callback_data="funding_menu",
            ),
        ],

        [
            InlineKeyboardButton(
                "🌐 Idioma",
                callback_data="language",
            ),

            InlineKeyboardButton(
                "⚙️ Configuración",
                callback_data="settings",
            ),
        ],
    ]

    if (
        user_id is not None
        and is_admin(user_id)
    ):

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🛠️ Administración",
                    callback_data="admin_menu",
                )
            ]
        )

    return InlineKeyboardMarkup(
        keyboard
    )

# ============================================================
# 💎 MENÚ DE FONDEO — QVAFUNDED
# ============================================================

def funding_menu():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🏦 ¿Qué es QvaFunded?",
                    callback_data="funding_about",
                )
            ],
            [
                InlineKeyboardButton(
                    "💼 Tipos de cuentas",
                    callback_data="funding_accounts",
                )
            ],
            [
                InlineKeyboardButton(
                    "⭐ QVA Flex",
                    callback_data="funding_flex",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚠️ Importante",
                    callback_data="funding_warning",
                )
            ],
            [
                InlineKeyboardButton(
                    "🚀 Ir a QvaFunded",
                    callback_data="funding_link",
                )
            ],
[
    InlineKeyboardButton(
        "🔙 Volver",
        callback_data="main_menu",
    )
],
        ]
    )


async def show_funding_menu(query):

    text = (
        "💎 <b>CUENTAS DE FONDEO</b>\n\n"
        "Accede a información sobre QvaFunded, "
        "sus programas de fondeo y las condiciones "
        "de sus cuentas.\n\n"
        "🏦 Conoce QvaFunded\n"
        "💼 Compara sus cuentas\n"
        "⭐ Conoce QVA Flex\n"
        "⚠️ Revisa las condiciones importantes\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=funding_menu(),
        parse_mode="HTML",
    )


async def show_funding_about(query):

    text = (
        "🏦 <b>¿QUÉ ES QVAFUNDED?</b>\n\n"
        "QvaFunded es una empresa de fondeo que ofrece "
        "programas de evaluación para traders.\n\n"
        "Su modelo permite al trader demostrar su capacidad "
        "de gestión y operativa siguiendo las reglas "
        "establecidas por cada programa.\n\n"
        "📊 Ofrece diferentes tipos de cuentas y tamaños "
        "de capital.\n\n"
        "💻 Consulta siempre las condiciones actuales "
        "antes de adquirir una evaluación.\n\n"
        "⚠️ Las reglas, precios y condiciones pueden cambiar."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💼 Tipos de cuentas",
                        callback_data="funding_accounts",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⭐ Ver QVA Flex",
                        callback_data="funding_flex",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="funding_menu",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )


async def show_funding_accounts(query):

    text = (
        "💼 <b>TIPOS DE CUENTAS QVAFUNDED</b>\n\n"
        "QvaFunded ofrece diferentes programas de "
        "evaluación con distintas condiciones.\n\n"
        "⭐ <b>QVA Flex</b>\n"
        "Programa de 1 fase con objetivo del 6% y "
        "trailing drawdown.\n\n"
        "💼 <b>Profesional</b>\n"
        "Programa con condiciones y reglas propias.\n\n"
        "📊 <b>Ligera</b>\n"
        "Programa diseñado con condiciones diferentes "
        "de riesgo y evaluación.\n\n"
        "⚠️ Cada programa tiene sus propias reglas. "
        "Consulta siempre las condiciones vigentes "
        "directamente en QvaFunded."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⭐ Ver QVA Flex",
                        callback_data="funding_flex",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🚀 Ir a QvaFunded",
                        callback_data="funding_link",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="funding_menu",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )


async def show_funding_flex(query):

    text = (
        "⭐ <b>QVA FLEX — CUENTA $3K</b>\n\n"
        "🎯 <b>Objetivo:</b> $180 (6%)\n"
        "📊 <b>Evaluación:</b> 1 fase\n"
        "📉 <b>Drawdown:</b> Trailing EOD\n"
        "🛑 <b>Trailing inicial:</b> $120\n"
        "💰 <b>Pérdida diaria:</b> Ninguna\n"
        "📅 <b>Días mínimos:</b> Ninguno\n"
        "⚖️ <b>Consistencia:</b> 50%\n"
        "📰 <b>Trading en noticias:</b> Sí\n"
        "⚡ <b>Apalancamiento:</b> 1:100\n"
        "💵 <b>Reparto:</b> 80/20\n"
        "🤖 <b>EAs:</b> No permitidos\n"
        "⚡ <b>Scalping:</b> Sí\n\n"
        "📌 <b>Consistencia</b>\n"
        "El mejor día no puede superar el 50% del "
        "objetivo de beneficio.\n\n"
        "📌 <b>Trailing EOD</b>\n"
        "El drawdown se calcula según las condiciones "
        "establecidas por QvaFunded.\n\n"
        "⚠️ Las reglas, precios y promociones pueden "
        "cambiar. Consulta siempre las condiciones "
        "actuales directamente en QvaFunded."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🚀 Ir a QvaFunded",
                        callback_data="funding_link",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⚠️ Importante",
                        callback_data="funding_warning",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="funding_menu",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )


async def show_funding_warning(query):

    text = (
        "⚠️ <b>IMPORTANTE — CUENTAS DE FONDEO</b>\n\n"
        "Las señales de <b>Apex Quant</b> NO deben "
        "utilizarse para intentar superar un challenge "
        "de QvaFunded.\n\n"
        "🚫 No utilices las señales de Apex Quant como "
        "método automático o directo para intentar "
        "aprobar una evaluación de fondeo.\n\n"
        "📋 El trader es responsable de realizar su propia "
        "operativa y de cumplir en todo momento las reglas "
        "establecidas por QvaFunded.\n\n"
        "⚠️ Apex Quant no garantiza la aprobación de ningún "
        "challenge ni los resultados de una cuenta de fondeo.\n\n"
        "📌 Antes de operar una cuenta de fondeo, revisa "
        "siempre las reglas y condiciones vigentes de "
        "QvaFunded."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🚀 Ir a QvaFunded",
                        callback_data="funding_link",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="funding_menu",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )


async def show_funding_link(query):

    referral_url = os.getenv(
        "QVAFUNDED_REFERRAL_URL",
        "https://www.qvafunded.live",
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Abrir QvaFunded",
                    url=referral_url,
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="funding_menu",
                )
            ],
        ]
    )

    text = (
        "🚀 <b>QVA FUNDED</b>\n\n"
        "Accede directamente a QvaFunded para consultar "
        "las cuentas, precios y condiciones actuales.\n\n"
        "💎 Revisa siempre las reglas vigentes antes de "
        "adquirir cualquier evaluación.\n\n"
        "👇 Pulsa el botón para acceder:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )

# ============================================================
# MENÚ MERCADOS
# ============================================================

def markets_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "📅 Calendario económico",
                callback_data="calendar",
            )
        ],

        [
            InlineKeyboardButton(
                "🚨 Noticias alto impacto",
                callback_data="high_news",
            )
        ],

        [
            InlineKeyboardButton(
                "💱 Noticias por divisa",
                callback_data="currency_news",
            )
        ],

        [
            InlineKeyboardButton(
                "⚠️ Riesgo de noticias",
                callback_data="news_risk",
            )
        ],

        [
            InlineKeyboardButton(
                "📈 Análisis diario",
                callback_data="daily_analysis",
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ Menú principal",
                callback_data="main_menu",
            )
        ],
    ]

    return InlineKeyboardMarkup(
        keyboard
    )


# ============================================================
# MENÚ CALENDARIO
# ============================================================

def calendar_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "📅 Hoy",
                callback_data="calendar_today",
            ),

            InlineKeyboardButton(
                "📅 Mañana",
                callback_data="calendar_tomorrow",
            ),
        ],

        [
            InlineKeyboardButton(
                "🗓️ Esta semana",
                callback_data="calendar_week",
            )
        ],

        [
            InlineKeyboardButton(
                "🚨 Alto impacto",
                callback_data="calendar_high",
            )
        ],

        [
            InlineKeyboardButton(
                "💱 Por divisa",
                callback_data="calendar_currency",
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data="calendar_refresh",
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ Mercados",
                callback_data="markets",
            )
        ],
    ]

    return InlineKeyboardMarkup(
        keyboard
    )


# ============================================================
# MENÚ DIVISAS
# ============================================================

def currency_menu():

    currencies = [

        ("🇺🇸 USD", "USD"),
        ("🇪🇺 EUR", "EUR"),
        ("🇬🇧 GBP", "GBP"),
        ("🇯🇵 JPY", "JPY"),
        ("🇨🇭 CHF", "CHF"),
        ("🇨🇦 CAD", "CAD"),
        ("🇦🇺 AUD", "AUD"),
        ("🇳🇿 NZD", "NZD"),
    ]

    keyboard = []

    for i in range(
        0,
        len(currencies),
        2
    ):

        row = []

        for name, code in currencies[
            i:i + 2
        ]:

            row.append(
                InlineKeyboardButton(
                    name,
                    callback_data=(
                        f"currency_{code}"
                    ),
                )
            )

        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                "⬅️ Calendario",
                callback_data="calendar",
            )
        ]
    )

    return InlineKeyboardMarkup(
        keyboard
    )


# ============================================================
# BOTÓN MENÚ PRINCIPAL
# ============================================================

def back_main_menu():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⬅️ Menú principal",
                    callback_data="main_menu",
                )
            ]
        ]
    )


# ============================================================
# SUSCRIPCIONES DE SEÑALES — ALMACENAMIENTO
# ============================================================

def load_subscriptions():

    """Carga las suscripciones desde JSON."""

    try:

        if not os.path.exists(
            SUBSCRIPTIONS_FILE
        ):

            return {}

        with open(
            SUBSCRIPTIONS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return (
            data
            if isinstance(data, dict)
            else {}
        )

    except Exception as error:

        logger.error(
            "Error cargando suscripciones: %s",
            error
        )

        return {}


def save_subscriptions(data):

    """Guarda las suscripciones de forma atómica."""

    try:

        temp_file = (
            f"{SUBSCRIPTIONS_FILE}.tmp"
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

    except Exception as error:

        logger.error(
            "Error guardando suscripciones: %s",
            error
        )


def get_subscription(user_id):

    """Devuelve la suscripción de un usuario."""

    data = load_subscriptions()

    return data.get(
        str(user_id)
    )


def activate_subscription(user_id):

    """Activa o renueva una suscripción por 30 días."""

    now = datetime.now()

    current = get_subscription(
        user_id
    )

    if current:

        try:

            current_expiry = (
                datetime.fromisoformat(
                    current.get(
                        "expires_at",
                        ""
                    )
                )
            )

        except (
            TypeError,
            ValueError
        ):

            current_expiry = now

        start_date = (
            current_expiry
            if current_expiry > now
            else now
        )

    else:

        start_date = now

    expires_at = (
        start_date
        + timedelta(
            days=SIGNALS_DURATION_DAYS
        )
    )

    data = load_subscriptions()

    data[str(user_id)] = {

        "telegram_id": int(
            user_id
        ),

        "status": "active",

        "started_at": (
            start_date.isoformat()
        ),

        "expires_at": (
            expires_at.isoformat()
        ),

        "price_usdt": (
            SIGNALS_PRICE_USDT
        ),

        "payment_network": "BEP20",
    }

    save_subscriptions(
        data
    )

    return data[
        str(user_id)
    ]


# ============================================================
# CALENDARIO — PETICIÓN API
# ============================================================

async def fetch_calendar_events(
    start_date=None,
    end_date=None,
    impact=None,
    currency=None,
):

    params = {}

    if start_date:
        params["start_date"] = (
            start_date.strftime("%Y-%m-%d")
            if hasattr(start_date, "strftime")
            else str(start_date)
        )

    if end_date:
        params["end_date"] = (
            end_date.strftime("%Y-%m-%d")
            if hasattr(end_date, "strftime")
            else str(end_date)
        )

    if impact:
        params["impact"] = impact

    if currency:
        params["currency"] = currency

    try:

        url = (
            f"{FINANCE_CALENDAR_BASE}/events"
        )

        query_string = urlencode(
            params
        )

        if query_string:
            url = (
                f"{url}?{query_string}"
            )

        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "ApexQuantBot/1.0"
                )
            },
        )

        with urlopen(
            request,
            timeout=15
        ) as response:

            raw = response.read()

        data = json.loads(
            raw.decode(
                "utf-8"
            )
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

    except Exception as error:

        logger.error(
            "Error consultando calendario: %s",
            error
        )

    return []


def normalize_event(event):

    if not isinstance(
        event,
        dict
    ):
        return None

    date_value = (
        event.get("date")
        or event.get("datetime")
        or event.get("date_time")
        or event.get("time")
        or ""
    )

    currency = (
        event.get("currency")
        or event.get("country")
        or event.get("ccy")
        or ""
    )

    impact = (
        event.get("impact")
        or event.get("importance")
        or ""
    )

    title = (
        event.get("title")
        or event.get("event")
        or event.get("name")
        or "Evento económico"
    )

    actual = (
        event.get("actual")
        or event.get("act")
        or ""
    )

    forecast = (
        event.get("forecast")
        or event.get("consensus")
        or event.get("cons")
        or ""
    )

    previous = (
        event.get("previous")
        or event.get("prev")
        or ""
    )

    return {
        "date": str(date_value),
        "currency": str(currency),
        "impact": str(impact),
        "title": str(title),
        "actual": str(actual),
        "forecast": str(forecast),
        "previous": str(previous),
    }


def event_impact_label(impact):

    value = str(
        impact
    ).strip().lower()

    if value in (
        "high",
        "alto",
        "3",
        "3.0",
    ):

        return "🔴 ALTO"

    if value in (
        "medium",
        "moderate",
        "medio",
        "2",
        "2.0",
    ):

        return "🟠 MEDIO"

    if value in (
        "low",
        "bajo",
        "1",
        "1.0",
    ):

        return "🟢 BAJO"

    return (
        f"⚪ {impact}"
        if impact
        else "⚪ N/D"
    )


def format_calendar_event(
    event
):

    item = normalize_event(
        event
    )

    if not item:
        return ""

    lines = []

    date_text = item["date"]

    if date_text:
        lines.append(
            f"🕒 {date_text}"
        )

    lines.append(
        f"{event_impact_label(item['impact'])} "
        f"• {item['currency']}"
    )

    lines.append(
        f"📌 {item['title']}"
    )

    values = []

    if item["actual"]:
        values.append(
            f"Act: {item['actual']}"
        )

    if item["forecast"]:
        values.append(
            f"Cons: {item['forecast']}"
        )

    if item["previous"]:
        values.append(
            f"Anterior: {item['previous']}"
        )

    if values:
        lines.append(
            " | ".join(values)
        )

    return "\n".join(
        lines
    )


def calendar_events_text(
    events,
    title="📅 Calendario económico",
):

    if not events:
        return (
            f"*{title}*\n\n"
            "No se encontraron eventos "
            "para el periodo seleccionado.\n\n"
            "🔗 Datos: FinanceCalendar.com"
        )

    normalized = []

    for event in events:

        item = normalize_event(
            event
        )

        if item:
            normalized.append(
                item
            )

    normalized.sort(
        key=lambda x: (
            x.get("date", "")
            or ""
        )
    )

    blocks = []

    for item in normalized[:30]:

        block = format_calendar_event(
            item
        )

        if block:
            blocks.append(
                block
            )

    if not blocks:
        return (
            f"*{title}*\n\n"
            "No se encontraron eventos "
            "válidos para mostrar.\n\n"
            "🔗 Datos: FinanceCalendar.com"
        )

    return (
        f"*{title}*\n\n"
        + "\n\n".join(
            blocks
        )
        + "\n\n🔗 Datos: FinanceCalendar.com"
    )


def get_day_range(offset=0):

    today = datetime.now().date()

    target = (
        today
        + timedelta(
            days=offset
        )
    )

    return target, target


def get_week_range():

    today = datetime.now().date()

    start = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    end = (
        start
        + timedelta(
            days=6
        )
    )

    return start, end


async def show_calendar_today(
    query
):

    start, end = get_day_range(
        0
    )

    events = await asyncio.to_thread(
        fetch_calendar_events,
        start,
        end,
    )

    await query.edit_message_text(
        calendar_events_text(
            events,
            "📅 Eventos de hoy",
        ),
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


async def show_calendar_tomorrow(
    query
):

    start, end = get_day_range(
        1
    )

    events = await asyncio.to_thread(
        fetch_calendar_events,
        start,
        end,
    )

    await query.edit_message_text(
        calendar_events_text(
            events,
            "📅 Eventos de mañana",
        ),
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


async def show_calendar_week(
    query
):

    start, end = get_week_range()

    events = await asyncio.to_thread(
        fetch_calendar_events,
        start,
        end,
    )

    await query.edit_message_text(
        calendar_events_text(
            events,
            "🗓️ Eventos de esta semana",
        ),
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


async def show_calendar_high(
    query
):

    start, end = get_week_range()

    events = await asyncio.to_thread(
        fetch_calendar_events,
        start,
        end,
        impact="high",
    )

    await query.edit_message_text(
        calendar_events_text(
            events,
            "🚨 Eventos de alto impacto",
        ),
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


async def show_calendar_currency(
    query
):

    text = (
        "💱 *Noticias por divisa*\n\n"
        "Selecciona la divisa:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=currency_menu(),
    )


async def show_calendar_currency_events(
    query,
    currency,
):

    start, end = get_week_range()

    events = await asyncio.to_thread(
        fetch_calendar_events,
        start,
        end,
        currency=currency,
    )

    await query.edit_message_text(
        calendar_events_text(
            events,
            f"💱 Eventos {currency}",
        ),
        parse_mode="Markdown",
        reply_markup=currency_menu(),
    )


async def show_calendar_refresh(
    query
):

    start, end = get_day_range(
        0
    )

    events = await asyncio.to_thread(
        fetch_calendar_events,
        start,
        end,
    )

    await query.edit_message_text(
        calendar_events_text(
            events,
            "🔄 Calendario actualizado",
        ),
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


# ============================================================
# NOTICIAS / RIESGO
# ============================================================

async def show_high_news(
    query
):

    start, end = get_week_range()

    events = await asyncio.to_thread(
        fetch_calendar_events,
        start,
        end,
        impact="high",
    )

    text = calendar_events_text(
        events,
        "🚨 Noticias de alto impacto",
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=markets_menu(),
    )


async def show_currency_news(
    query
):

    await show_calendar_currency(
        query
    )


async def show_news_risk(
    query
):

    text = (
        "⚠️ *Riesgo de noticias*\n\n"
        "Los eventos económicos de alto impacto "
        "pueden aumentar la volatilidad y provocar "
        "movimientos rápidos en los precios.\n\n"
        "Antes de abrir una operación, revisa el "
        "calendario económico y considera la posible "
        "exposición a noticias.\n\n"
        "⚠️ Esta información es educativa y no "
        "garantiza resultados."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=markets_menu(),
    )


# ============================================================
# ANÁLISIS DIARIO
# ============================================================

async def show_daily_analysis(
    query
):

    text = (
        "📈 *Análisis diario — Apex Quant*\n\n"

        "🧭 *Estructura de análisis*\n"
        "H4 – Dirección\n"
        "H1 – Liquidez\n"
        "M5 – Entrada\n\n"

        "🔎 *Elementos analizados*\n"
        "• BOS\n"
        "• FVG\n"
        "• Liquidez\n"
        "• Volumen\n"
        "• RSI 14\n"
        "• HH / HL\n"
        "• Estructura de mercado\n\n"

        "💱 *Instrumentos*\n"
        "• EUR/USD\n"
        "• GBP/USD\n"
        "• GBP/JPY\n\n"

        "⚠️ El análisis es una estimación basada en "
        "condiciones de mercado y no garantiza resultados."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=markets_menu(),

                ),
    )


async def show_copy_info(query):
    text = (
        "📘 *¿Cómo funciona CopyTrading?*\n\n"
        "CopyTrading permite que las operaciones "
        "de una estrategia o proveedor puedan ser "
        "replicadas automáticamente en la cuenta "
        "de un seguidor.\n\n"
        "📊 El resultado de cada usuario puede variar "
        "según el tamaño de su cuenta, configuración "
        "de riesgo, volumen y condiciones del mercado.\n\n"
        "⚙️ Antes de activar el servicio, revisa "
        "las condiciones disponibles y configura "
        "los parámetros de riesgo de tu cuenta.\n\n"
        "⚠️ *Importante:*\n"
        "• No existen ganancias garantizadas.\n"
        "• Las operaciones pueden generar pérdidas.\n"
        "• El rendimiento pasado no garantiza "
        "resultados futuros.\n"
        "• Cada usuario es responsable de su propia "
        "cuenta y de la configuración que seleccione."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📈 Seguir ApexQuant",
                callback_data="copy_follow",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ CopyTrading",
                callback_data="copytrading",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# REFERIDOS — DETALLE DE 3 NIVELES
# ============================================================

async def show_referral_levels(query):
    user = query.from_user

    register_user(user)

    levels = get_referral_levels(
        user.id
    )

    level_1_count = len(
        levels["level_1"]
    )

    level_2_count = len(
        levels["level_2"]
    )

    level_3_count = len(
        levels["level_3"]
    )

    total_count = (
        level_1_count
        + level_2_count
        + level_3_count
    )

    text = (
        "👥 *Tus referidos por nivel*\n\n"
        f"🥇 Nivel 1: *{level_1_count}*\n"
        f"🥈 Nivel 2: *{level_2_count}*\n"
        f"🥉 Nivel 3: *{level_3_count}*\n\n"
        f"👥 *Total de los 3 niveles: "
        f"{total_count}*\n\n"
        "📌 *Nivel 1:* personas que entraron "
        "directamente mediante tu enlace.\n\n"
        "📌 *Nivel 2:* personas invitadas por "
        "tus referidos de Nivel 1.\n\n"
        "📌 *Nivel 3:* personas invitadas por "
        "tus referidos de Nivel 2."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔗 Mi enlace",
                callback_data="referrals",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Menú principal",
                callback_data="main_menu",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# CALENDARIO — HOY
# ============================================================

async def calendar_today(query):
    today = today_date()

    await show_events(
        query,
        "Calendario de hoy",
        today,
        today,
    )


# ============================================================
# CALENDARIO — MAÑANA
# ============================================================

async def calendar_tomorrow(query):
    tomorrow = tomorrow_date()

    await show_events(
        query,
        "Calendario de mañana",
        tomorrow,
        tomorrow,
    )


# ============================================================
# CALENDARIO — ESTA SEMANA
# ============================================================

async def calendar_week(query):
    monday, sunday = week_dates()

    await show_events(
        query,
        "Calendario de esta semana",
        monday,
        sunday,
    )


# ============================================================
# CALENDARIO — ALTO IMPACTO
# ============================================================

async def calendar_high(query):
    today = today_date()
    end_date = today + timedelta(days=7)

    await show_events(
        query,
        "Eventos de alto impacto",
        today,
        end_date,
        impact="high",
    )


# ============================================================
# CALENDARIO — POR DIVISA
# ============================================================

async def calendar_currency(query):
    await show_currency_news(query)


# ============================================================
# ACTUALIZAR CALENDARIO
# ============================================================

async def calendar_refresh(query):
    today = today_date()
    end_date = today + timedelta(days=7)

    await show_events(
        query,
        "Calendario actualizado",
        today,
        end_date,
    )


# ============================================================
# REFERIDOS
# ============================================================

async def show_referrals(query, context):
    user = query.from_user

    register_user(user)

    telegram_id = user.id

    bot_username = context.bot.username or "ApexQuantFXBot"

    invite_link = (
        f"https://t.me/{bot_username}"
        f"?start=ref_{telegram_id}"
    )

    referral_count = get_referral_count(
        telegram_id
    )

    text = (
        "👥 *Programa de Referidos Apex Quant*\n\n"
        "Invita a otras personas a conocer "
        "Apex Quant utilizando tu enlace personal.\n\n"
        "🔗 *Tu enlace personal:*\n"
        f"`{invite_link}`\n\n"
        "🔢 *Tu Telegram ID:*\n"
        f"`{telegram_id}`\n\n"
        f"👥 *Referidos registrados:* "
        f"*{referral_count}*\n\n"
        "📌 Cada persona debe entrar mediante "
        "tu enlace y pulsar *START* para que "
        "el sistema pueda registrar la invitación.\n\n"
        "💰 *Comisiones por suscripciones:*\n"
        "🥇 Nivel 1: *5%*\n"
        "🥈 Nivel 2: *3%*\n"
        "🥉 Nivel 3: *2%*\n\n"
        "Las comisiones se calculan sobre las "
        "suscripciones de señales pagadas por tus referidos "
        "en los tres niveles.\n\n"
        "🛡️ El sistema utiliza el ID único de "
        "Telegram para evitar autorreferidos y "
        "duplicados."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# IDIOMA
# ============================================================

async def show_language(query):
    text = (
        "🌐 *Idioma*\n\n"
        "Selecciona el idioma del bot:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🇪🇸 Español",
                callback_data="language_es",
            ),
            InlineKeyboardButton(
                "🇺🇸 English",
                callback_data="language_en",
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ Menú principal",
                callback_data="main_menu",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# CONFIGURACIÓN
# ============================================================

async def show_settings(query):
    text = (
        "⚙️ *Configuración*\n\n"
        "La sección de configuración se encuentra "
        "en preparación.\n\n"
        "Próximamente podrás gestionar preferencias "
        "de idioma, notificaciones y otras opciones."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# MANEJADOR PRINCIPAL DE BOTONES
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer()

    data = query.data

    logger.info(
        "Callback recibido: %s",
        data,
    )

    # ========================================================
    # MENÚ PRINCIPAL
    # ========================================================

    if data == "main_menu":
        text = (
            "🔥 *Apex Quant*\n\n"
            "Selecciona una opción:"
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(query.from_user.id),
        )

        return

    # ========================================================
    # MERCADOS
    # ========================================================

    if data == "markets":
        await show_markets(query)
        return

    # ========================================================
    # SEÑALES
    # ========================================================

    if data == "signals":
        await show_signals(query)
        return

    # ========================================================
    # COPYTRADING
    # ========================================================

    if data == "copytrading":
        await show_copytrading(query)
        return

    if data == "copy_register":
        await show_copy_register(query)
        return

    if data == "copy_follow":
        await show_copy_follow(query)
        return

    if data == "copy_info":
        await show_copy_info(query)
        return

    # ========================================================
    # 💎 FONDEO — QVAFUNDED
    # ========================================================

    if data == "funding_menu":
        await show_funding_menu(query)
        return

    if data == "funding_about":
        await show_funding_about(query)
        return

    if data == "funding_accounts":
        await show_funding_accounts(query)
        return

    if data == "funding_flex":
        await show_funding_flex(query)
        return

    if data == "funding_warning":
        await show_funding_warning(query)
        return

    if data == "funding_link":
        await show_funding_link(query)
        return

    # ========================================================
    # ADMINISTRACIÓN
    # ========================================================

    if data == "admin_menu":
        await show_admin_menu(query)
        return

    if data == "admin_send_signal":
        if not is_admin(query.from_user.id):
            await query.answer(
                "⛔ No tienes permiso.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "📡 *Enviar señal*\n\n"
            "🚧 Formulario de señales en preparación.\n\n"
            "En el siguiente paso construiremos "
            "el formulario completo.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Administración",
                            callback_data="admin_menu",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 Menú principal",
                            callback_data="main_menu",
                        )
                    ],
                ]
            ),
        )

        return

    # ========================================================
    # HISTORIAL DE SEÑALES — ADMIN
    # ========================================================

    if data == "admin_signal_history":
        if not is_admin(query.from_user.id):
            await query.answer(
                "⛔ No tienes permiso.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "📊 *Historial de señales*\n\n"
            "🚧 Esta sección se encuentra en preparación.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Administración",
                            callback_data="admin_menu",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 Menú principal",
                            callback_data="main_menu",
                        )
                    ],
                ]
            ),
        )

        return

    # ========================================================
    # USUARIOS ACTIVOS — ADMIN
    # ========================================================

    if data == "admin_active_users":
        if not is_admin(query.from_user.id):
            await query.answer(
                "⛔ No tienes permiso.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "👥 *Suscriptores activos*\n\n"
            "🚧 Esta sección se encuentra en preparación.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Administración",
                            callback_data="admin_menu",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 Menú principal",
                            callback_data="main_menu",
                        )
                    ],
                ]
            ),
        )

        return

    # ========================================================
    # ESTADÍSTICAS — ADMIN
    # ========================================================

    if data == "admin_statistics":
        if not is_admin(query.from_user.id):
            await query.answer(
                "⛔ No tienes permiso.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "📈 *Estadísticas*\n\n"
            "🚧 Esta sección se encuentra en preparación.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Administración",
                            callback_data="admin_menu",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 Menú principal",
                            callback_data="main_menu",
                        )
                    ],
                ]
            ),
        )

        return

    # ========================================================
    # SUSCRIPCIÓN DE SEÑALES
    # ========================================================

    if data == "signal_subscribe":
        await show_signal_subscription(query)
        return

    if data == "signal_payment":
        await show_signal_payment(query)
        return

    if data == "signal_status":
        await show_signal_status(query)
        return

    # ========================================================
    # REFERIDOS
    # ========================================================

    if data == "referrals":
        await show_referrals(query, context)
        return

    if data == "referral_levels":
        await show_referral_levels(query)
        return

    # ========================================================
    # IDIOMA
    # ========================================================

    if data == "language":
        await show_language(query)
        return

    if data == "language_es":
        text = (
            "🇪🇸 *Español seleccionado*\n\n"
            "El idioma español está seleccionado."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )

        return

    if data == "language_en":
        text = (
            "🇺🇸 *English selected*\n\n"
            "English is currently selected."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )

        return

    # ========================================================
    # CONFIGURACIÓN
    # ========================================================

    if data == "settings":
        await show_settings(query)
        return
    )

            reply_markup=back_main_menu(),
        )

        return

    # ========================================================
    # CALENDARIO
    # ========================================================

    if data == "calendar":
        await show_calendar(query)
        return

    if data == "high_news":
        await show_high_news(query)
        return

    if data == "currency_news":
        await show_currency_news(query)
        return

    if data == "news_risk":
        await show_news_risk(query)
        return

    if data == "daily_analysis":
        await show_daily_analysis(query)
        return

    # ========================================================
    # OPCIONES DEL CALENDARIO
    # ========================================================

    if data == "calendar_today":
        await calendar_today(query)
        return

    if data == "calendar_tomorrow":
        await calendar_tomorrow(query)
        return

    if data == "calendar_week":
        await calendar_week(query)
        return

    if data == "calendar_high":
        await calendar_high(query)
        return

    if data == "calendar_currency":
        await calendar_currency(query)
        return

    if data == "calendar_refresh":
        await calendar_refresh(query)
        return

    # ========================================================
    # CALENDARIO POR DIVISA
    # ========================================================

    if data.startswith("currency_"):
        currency = data.replace(
            "currency_",
            "",
            1,
        )

        await currency_events(
            query,
            currency,
        )

        return

    # ========================================================
    # OPCIÓN NO DISPONIBLE
    # ========================================================

    text = (
        "⚠️ Opción no disponible actualmente."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# ACTIVACIÓN MANUAL DE SUSCRIPCIONES
# ============================================================

async def activate_signal_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Uso administrativo: /activate ID_TELEGRAM"""

    user = update.effective_user

    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text(
                "⛔ No tienes permiso para utilizar este comando."
            )
        return

    if not context.args:
        await update.message.reply_text(
            "Uso:\n/activate ID_TELEGRAM"
        )
        return

    target_id = context.args[0].strip()

    if not target_id.isdigit():
        await update.message.reply_text(
            "❌ El Telegram ID debe ser numérico."
        )
        return

    subscription = activate_subscription(
        int(target_id)
    )

    expires_at = datetime.fromisoformat(
        subscription["expires_at"]
    ).strftime("%d/%m/%Y")

    await update.message.reply_text(
        "✅ *Suscripción activada*\n\n"
        f"🔢 Telegram ID: `{target_id}`\n"
        f"💵 Suscripción: *${SIGNALS_PRICE_USDT} USDT / 30 días*\n"
        "🌐 Red: *BEP20*\n"
        f"📅 Vencimiento: *{expires_at}*",
        parse_mode="Markdown",
    )


# ============================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# ============================================================

def build_application():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "activate",
            activate_signal_command,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler,
        )
    )

    return application


# ============================================================
# INICIO DEL BOT
# ============================================================

def main():
    logger.info(
        "Iniciando Apex Quant..."
    )

    application = build_application()

    logger.info(
        "Apex Quant iniciado correctamente."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()
