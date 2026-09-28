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
# CONFIGURACIÓN
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Falta la variable de entorno BOT_TOKEN")


REFERRALS_FILE = os.getenv(
    "REFERRALS_FILE",
    "referrals.json",
)

SUBSCRIPTIONS_FILE = os.getenv(
    "SUBSCRIPTIONS_FILE",
    "subscriptions.json",
)

SIGNALS_PRICE_USDT = 30
SIGNALS_DURATION_DAYS = 30

USDT_BEP20_ADDRESS = os.getenv(
    "USDT_BEP20_ADDRESS",
    "",
)

ADMIN_TELEGRAM_ID = os.getenv(
    "ADMIN_TELEGRAM_ID",
    "",
).strip()

# ============================================================
# 🔗 ONEROYAL — ENLACES DE APEX QUANT
# ============================================================

# Enlace de IB de Apex Quant
ONEROYAL_IB_URL = os.getenv(
    "ONEROYAL_IB_URL",
    "",
).strip()

# Enlace específico para CopyTrading de Apex Quant
ONEROYAL_COPYTRADING_URL = os.getenv(
    "ONEROYAL_COPYTRADING_URL",
    "",
).strip()

# ============================================================
# 📅 CALENDARIO ECONÓMICO
# ============================================================

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
# VERIFICACIÓN DE ADMINISTRADOR
# ============================================================

def is_admin(user_id):

    admin_id = os.getenv(
        "ADMIN_TELEGRAM_ID"
    )

    if not admin_id:
        return False

    return str(user_id) == str(admin_id)


# ============================================================
# ALMACENAMIENTO DE REFERIDOS
# ============================================================

def load_referrals():
    """Carga los datos de referidos desde JSON."""

    try:

        if not os.path.exists(
            REFERRALS_FILE
        ):
            return {
                "users": {},
                "referrals": {},
            }

        with open(
            REFERRALS_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "Formato de referidos inválido"
            )

        data.setdefault(
            "users",
            {},
        )

        data.setdefault(
            "referrals",
            {},
        )

        return data

    except Exception as error:

        logger.error(
            "Error cargando referidos: %s",
            error,
        )

        return {
            "users": {},
            "referrals": {},
        }


def save_referrals(data):
    """Guarda los datos de referidos."""

    try:

        temp_file = (
            f"{REFERRALS_FILE}.tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            temp_file,
            REFERRALS_FILE,
        )

    except Exception as error:

        logger.error(
            "Error guardando referidos: %s",
            error,
        )


def register_user(user):
    """Registra un usuario mediante su Telegram ID."""

    if not user:
        return

    data = load_referrals()

    user_id = str(
        user.id
    )

    if user_id not in data["users"]:

        data["users"][user_id] = {
            "telegram_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "referred_by": None,
        }

    else:

        data["users"][user_id][
            "username"
        ] = user.username or ""

        data["users"][user_id][
            "first_name"
        ] = user.first_name or ""

    data["referrals"].setdefault(
        user_id,
        [],
    )

    save_referrals(
        data
    )

    return data


def process_referral(
    user,
    start_parameter,
):
    """
    Procesa enlaces:

    /start ref_123456789
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
            parameter,
        )

        return False

    user_id = str(
        user.id
    )

    if referrer_id == user_id:

        logger.info(
            "Auto-referencia bloqueada para Telegram ID %s",
            user_id,
        )

        return False

    data = load_referrals()

    if user_id not in data["users"]:

        data["users"][user_id] = {
            "telegram_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "referred_by": None,
        }

    else:

        data["users"][user_id][
            "username"
        ] = user.username or ""

        data["users"][user_id][
            "first_name"
        ] = user.first_name or ""

    data["referrals"].setdefault(
        user_id,
        [],
    )

    if referrer_id not in data["users"]:

        data["users"][referrer_id] = {
            "telegram_id": int(
                referrer_id
            ),
            "username": "",
            "first_name": "",
            "referred_by": None,
        }

    if data["users"][user_id].get(
        "referred_by"
    ):

        save_referrals(
            data
        )

        return False

    data["referrals"].setdefault(
        referrer_id,
        [],
    )

    if user_id in data["referrals"][
        referrer_id
    ]:

        data["users"][user_id][
            "referred_by"
        ] = referrer_id

        save_referrals(
            data
        )

        return False

    data["referrals"][
        referrer_id
    ].append(
        user_id
    )

    data["users"][user_id][
        "referred_by"
    ] = referrer_id

    save_referrals(
        data
    )

    logger.info(
        "Nuevo referido registrado: %s -> %s",
        referrer_id,
        user_id,
    )

    return True


def get_referral_levels(
    user_id
):
    """
    Nivel 1 = referidos directos
    Nivel 2 = referidos de Nivel 1
    Nivel 3 = referidos de Nivel 2
    """

    data = load_referrals()

    root_id = str(
        user_id
    )

    level_1 = list(
        data["referrals"].get(
            root_id,
            [],
        )
    )

    level_2 = []

    for user_l1 in level_1:

        level_2.extend(
            data["referrals"].get(
                str(user_l1),
                [],
            )
        )

    level_3 = []

    for user_l2 in level_2:

        level_3.extend(
            data["referrals"].get(
                str(user_l2),
                [],
            )
        )

    return {
        "level_1": level_1,
        "level_2": level_2,
        "level_3": level_3,
    }


def get_referral_count(
    user_id
):

    return len(
        get_referral_levels(
            user_id
        )["level_1"]
    )


# ============================================================
# 🏠 MENÚ PRINCIPAL
# ============================================================

def main_menu(
    user_id=None
):

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
# 📋 COPYTRADING — ONEROYAL / APEX QUANT
# ============================================================

def copytrading_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "📈 Seguir Apex Quant",
                callback_data="copy_follow",
            )
        ],
        [
            InlineKeyboardButton(
                "🏦 Abrir cuenta OneRoyal",
                callback_data="copy_register",
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ ¿Cómo funciona?",
                callback_data="copy_info",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="main_menu",
            )
        ],
    ]

    return InlineKeyboardMarkup(
        keyboard
    )


async def show_copy_info(
    query
):

    text = (
        "📋 <b>COPYTRADING APEX QUANT</b>\n\n"
        "Apex Quant ofrece acceso a un servicio de "
        "CopyTrading mediante OneRoyal.\n\n"
        "📊 Puedes conectar una cuenta compatible y "
        "seguir las operaciones de Apex Quant.\n\n"
        "🏦 <b>Broker:</b> OneRoyal\n"
        "📋 <b>Servicio:</b> CopyTrading\n\n"
        "El objetivo es facilitar el acceso de los "
        "usuarios al servicio desde un único lugar.\n\n"
        "⚠️ El CopyTrading implica riesgo. Las operaciones "
        "pueden generar ganancias o pérdidas y los "
        "resultados anteriores no garantizan resultados "
        "futuros.\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=copytrading_menu(),
        parse_mode="HTML",
    )


async def show_copy_follow(
    query
):

    copy_url = os.getenv(
        "ONEROYAL_COPYTRADING_URL",
        "",
    ).strip()

    ib_url = os.getenv(
        "ONEROYAL_IB_URL",
        "",
    ).strip()

    keyboard = []

    if copy_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "📈 Acceder al CopyTrading",
                    url=copy_url,
                )
            ]
        )

    if ib_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🏦 Abrir cuenta OneRoyal",
                    url=ib_url,
                )
            ]
        )

    keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    "📋 Pasos para comenzar",
                    callback_data="copy_steps",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="copytrading",
                )
            ],
        ]
    )

    text = (
        "📈 <b>SEGUIR APEX QUANT</b>\n\n"
        "Para utilizar el CopyTrading de Apex Quant "
        "necesitas una cuenta compatible con el servicio.\n\n"
        "🏦 <b>Broker:</b> OneRoyal\n"
        "📊 <b>Servicio:</b> CopyTrading\n\n"
        "1️⃣ Abre tu cuenta con OneRoyal.\n"
        "2️⃣ Completa el proceso de verificación requerido.\n"
        "3️⃣ Abre una cuenta de trading compatible.\n"
        "4️⃣ Accede al servicio de CopyTrading.\n"
        "5️⃣ Sigue las instrucciones para conectar tu "
        "cuenta con Apex Quant.\n\n"
        "⚠️ Antes de operar, revisa las condiciones, "
        "comisiones y riesgos aplicables al servicio.\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="HTML",
    )


async def show_copy_register(
    query
):

    ib_url = os.getenv(
        "ONEROYAL_IB_URL",
        "",
    ).strip()

    keyboard = []

    if ib_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🚀 Registrarme en OneRoyal",
                    url=ib_url,
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "📋 Pasos para comenzar",
                callback_data="copy_steps",
            )
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="copytrading",
            )
        ]
    )

    text = (
        "🏦 <b>ABRIR CUENTA EN ONEROYAL</b>\n\n"
        "Si todavía no tienes una cuenta, puedes "
        "registrarte mediante el enlace de Apex Quant.\n\n"
        "1️⃣ Pulsa <b>Registrarme en OneRoyal</b>.\n"
        "2️⃣ Completa tus datos de registro.\n"
        "3️⃣ Completa el proceso de verificación "
        "requerido.\n"
        "4️⃣ Abre una cuenta de trading compatible "
        "con el servicio.\n"
        "5️⃣ Después podrás continuar con la configuración "
        "del CopyTrading.\n\n"
        "⚠️ Los requisitos, condiciones y disponibilidad "
        "de productos pueden cambiar. Consulta siempre "
        "la información vigente de OneRoyal."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="HTML",
    )


async def show_copy_steps(
    query
):

    copy_url = os.getenv(
        "ONEROYAL_COPYTRADING_URL",
        "",
    ).strip()

    keyboard = []

    if copy_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "📈 Acceder al CopyTrading",
                    url=copy_url,
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="copy_follow",
            )
        ]
    )

    text = (
        "📋 <b>PASOS PARA COMENZAR</b>\n\n"
        "1️⃣ <b>Regístrate</b>\n"
        "Crea tu cuenta de OneRoyal mediante el enlace "
        "proporcionado por Apex Quant.\n\n"
        "2️⃣ <b>Verificación</b>\n"
        "Completa el proceso KYC que corresponda a tu cuenta.\n\n"
        "3️⃣ <b>Cuenta de trading</b>\n"
        "Abre la cuenta compatible con el servicio que "
        "quieras utilizar.\n\n"
        "4️⃣ <b>CopyTrading</b>\n"
        "Accede al enlace específico del CopyTrading de "
        "Apex Quant.\n\n"
        "5️⃣ <b>Configuración</b>\n"
        "Sigue las instrucciones disponibles para conectar "
        "tu cuenta y comenzar a utilizar el servicio.\n\n"
        "⚠️ <b>Importante:</b>\n"
        "El CopyTrading implica riesgo. Las operaciones "
        "pueden generar pérdidas y los resultados anteriores "
        "no garantizan resultados futuros."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="HTML",
    )


# ============================================================
# 📊 MERCADOS
# ============================================================

async def markets_menu(
    query
):

    text = (
        "📊 <b>MERCADOS</b>\n\n"
        "Consulta los principales instrumentos que "
        "seguimos en Apex Quant.\n\n"
        "💱 EUR/USD\n"
        "💱 GBP/USD\n"
        "💱 GBP/JPY\n\n"
        "📌 Nuestro enfoque principal está orientado "
        "al DayTrading.\n\n"
        "⚠️ La información presentada no constituye "
        "asesoramiento financiero."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📅 Calendario económico",
                    callback_data="calendar",
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

    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def show_markets(
    query
):

    await markets_menu(
        query
    )


# ============================================================
# 📡 SEÑALES
# ============================================================

async def signals_menu(
    query
):

    text = (
        "📡 <b>SEÑALES APEX QUANT</b>\n\n"
        "Accede al servicio de señales de trading "
        "de Apex Quant.\n\n"
        "📊 Las señales son preparadas y enviadas "
        "por el administrador.\n\n"
        "💰 <b>Suscripción:</b> 30 USDT / 30 días\n"
        "🌐 <b>Red de pago:</b> BEP20\n\n"
        "⚠️ Las señales no garantizan resultados. "
        "Los mercados financieros implican riesgo "
        "de pérdida de capital.\n\n"
        "👇 Selecciona una opción:"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💳 Suscribirme",
                    callback_data="signal_subscription",
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 Estado de mi suscripción",
                    callback_data="signal_status",
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

    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def show_signals(
    query
):

    await signals_menu(
        query
    )


# ============================================================
# 💳 SUSCRIPCIONES DE SEÑALES
# ============================================================

def load_subscriptions():

    try:

        if not os.path.exists(
            SUBSCRIPTIONS_FILE
        ):
            return {}

        with open(
            SUBSCRIPTIONS_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            dict,
        ):
            return {}

        return data

    except Exception as error:

        logger.error(
            "Error cargando suscripciones: %s",
            error,
        )

        return {}


def save_subscriptions(
    data
):

    try:

        temp_file = (
            f"{SUBSCRIPTIONS_FILE}.tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            temp_file,
            SUBSCRIPTIONS_FILE,
        )

    except Exception as error:

        logger.error(
            "Error guardando suscripciones: %s",
            error,
        )


def is_subscription_active(
    user_id
):

    data = load_subscriptions()

    subscription = data.get(
        str(user_id)
    )

    if not subscription:
        return False

    if not subscription.get(
        "active",
        False,
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

        if expiration <= datetime.utcnow():
            return False

        return True

    except Exception:

        return False


async def show_signal_subscription(
    query
):

    address = USDT_BEP20_ADDRESS

    if address:

        payment_text = (
            "💳 <b>SUSCRIPCIÓN A SEÑALES</b>\n\n"
            f"💰 Precio: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
            f"📅 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
            "🌐 Red: <b>BEP20</b>\n\n"
            "💵 <b>Dirección USDT BEP20:</b>\n"
            f"<code>{address}</code>\n\n"
            "📌 Envía exactamente el importe indicado "
            "a la dirección anterior.\n\n"
            "Después del pago, envía al administrador "
            "el comprobante o hash de la transacción "
            "para verificarlo y activar tu suscripción.\n\n"
            "⚠️ Verifica cuidadosamente la red y la "
            "dirección antes de realizar el envío."
        )

    else:

        payment_text = (
            "💳 <b>SUSCRIPCIÓN A SEÑALES</b>\n\n"
            f"💰 Precio: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
            f"📅 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
            "🌐 Red: <b>BEP20</b>\n\n"
            "⚠️ La dirección de pago todavía no está "
            "configurada.\n\n"
            "Contacta con el administrador para recibir "
            "las instrucciones de pago."
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📋 Ver mi estado",
                    callback_data="signal_status",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="signals",
                )
            ],
        ]
    )

    await query.edit_message_text(
        text=payment_text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def show_signal_payment(
    query
):

    await show_signal_subscription(
        query
    )


async def show_signal_status(
    query
):

    user_id = query.from_user.id

    active = is_subscription_active(
        user_id
    )

    if active:

        data = load_subscriptions()

        subscription = data.get(
            str(user_id),
            {},
        )

        expires_at = subscription.get(
            "expires_at",
            "",
        )

        text = (
            "🟢 <b>SUSCRIPCIÓN ACTIVA</b>\n\n"
            "📡 Tienes acceso al servicio de "
            "señales de Apex Quant.\n\n"
            "📅 Válida hasta:\n"
            f"<b>{expires_at}</b>\n\n"
            "⚠️ Recuerda que las señales no garantizan "
            "resultados y existe riesgo de pérdida."
        )

    else:

        text = (
            "🔴 <b>SUSCRIPCIÓN INACTIVA</b>\n\n"
            "Actualmente no tienes una suscripción "
            "activa a las señales de Apex Quant.\n\n"
            "💰 Precio: <b>30 USDT / 30 días</b>\n"
            "🌐 Red: <b>BEP20</b>"
        )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💳 Suscribirme",
                        callback_data="signal_subscription",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="signals",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )

# ============================================================
# 📋 COPYTRADING — ONEROYAL / APEX QUANT
# ============================================================

def copytrading_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "📈 Seguir Apex Quant",
                callback_data="copy_follow",
            )
        ],
        [
            InlineKeyboardButton(
                "🏦 Abrir cuenta OneRoyal",
                callback_data="copy_register",
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ ¿Cómo funciona?",
                callback_data="copy_info",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="main_menu",
            )
        ],
    ]

    return InlineKeyboardMarkup(
        keyboard
    )


async def show_copy_info(
    query
):

    text = (
        "📋 <b>COPYTRADING APEX QUANT</b>\n\n"
        "Apex Quant ofrece acceso a un servicio de "
        "CopyTrading mediante OneRoyal.\n\n"
        "📊 Puedes conectar una cuenta compatible y "
        "seguir las operaciones de Apex Quant.\n\n"
        "🏦 <b>Broker:</b> OneRoyal\n"
        "📋 <b>Servicio:</b> CopyTrading\n\n"
        "El objetivo es facilitar el acceso de los "
        "usuarios al servicio desde un único lugar.\n\n"
        "⚠️ El CopyTrading implica riesgo. Las operaciones "
        "pueden generar ganancias o pérdidas y los "
        "resultados anteriores no garantizan resultados "
        "futuros.\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=copytrading_menu(),
        parse_mode="HTML",
    )


async def show_copy_follow(
    query
):

    copy_url = os.getenv(
        "ONEROYAL_COPYTRADING_URL",
        "",
    ).strip()

    ib_url = os.getenv(
        "ONEROYAL_IB_URL",
        "",
    ).strip()

    keyboard = []

    if copy_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "📈 Acceder al CopyTrading",
                    url=copy_url,
                )
            ]
        )

    if ib_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🏦 Abrir cuenta OneRoyal",
                    url=ib_url,
                )
            ]
        )

    keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    "📋 Pasos para comenzar",
                    callback_data="copy_steps",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="copytrading",
                )
            ],
        ]
    )

    text = (
        "📈 <b>SEGUIR APEX QUANT</b>\n\n"
        "Para utilizar el CopyTrading de Apex Quant "
        "necesitas una cuenta compatible con el servicio.\n\n"
        "🏦 <b>Broker:</b> OneRoyal\n"
        "📊 <b>Servicio:</b> CopyTrading\n\n"
        "1️⃣ Abre tu cuenta con OneRoyal.\n"
        "2️⃣ Completa el proceso de verificación requerido.\n"
        "3️⃣ Abre una cuenta de trading compatible.\n"
        "4️⃣ Accede al servicio de CopyTrading.\n"
        "5️⃣ Sigue las instrucciones para conectar tu "
        "cuenta con Apex Quant.\n\n"
        "⚠️ Antes de operar, revisa las condiciones, "
        "comisiones y riesgos aplicables al servicio.\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="HTML",
    )


async def show_copy_register(
    query
):

    ib_url = os.getenv(
        "ONEROYAL_IB_URL",
        "",
    ).strip()

    keyboard = []

    if ib_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🚀 Registrarme en OneRoyal",
                    url=ib_url,
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "📋 Pasos para comenzar",
                callback_data="copy_steps",
            )
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="copytrading",
            )
        ]
    )

    text = (
        "🏦 <b>ABRIR CUENTA EN ONEROYAL</b>\n\n"
        "Si todavía no tienes una cuenta, puedes "
        "registrarte mediante el enlace de Apex Quant.\n\n"
        "1️⃣ Pulsa <b>Registrarme en OneRoyal</b>.\n"
        "2️⃣ Completa tus datos de registro.\n"
        "3️⃣ Completa el proceso de verificación "
        "requerido.\n"
        "4️⃣ Abre una cuenta de trading compatible "
        "con el servicio.\n"
        "5️⃣ Después podrás continuar con la configuración "
        "del CopyTrading.\n\n"
        "⚠️ Los requisitos, condiciones y disponibilidad "
        "de productos pueden cambiar. Consulta siempre "
        "la información vigente de OneRoyal."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="HTML",
    )


async def show_copy_steps(
    query
):

    copy_url = os.getenv(
        "ONEROYAL_COPYTRADING_URL",
        "",
    ).strip()

    keyboard = []

    if copy_url:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "📈 Acceder al CopyTrading",
                    url=copy_url,
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data="copy_follow",
            )
        ]
    )

    text = (
        "📋 <b>PASOS PARA COMENZAR</b>\n\n"
        "1️⃣ <b>Regístrate</b>\n"
        "Crea tu cuenta de OneRoyal mediante el enlace "
        "proporcionado por Apex Quant.\n\n"
        "2️⃣ <b>Verificación</b>\n"
        "Completa el proceso KYC que corresponda a tu cuenta.\n\n"
        "3️⃣ <b>Cuenta de trading</b>\n"
        "Abre la cuenta compatible con el servicio que "
        "quieras utilizar.\n\n"
        "4️⃣ <b>CopyTrading</b>\n"
        "Accede al enlace específico del CopyTrading de "
        "Apex Quant.\n\n"
        "5️⃣ <b>Configuración</b>\n"
        "Sigue las instrucciones disponibles para conectar "
        "tu cuenta y comenzar a utilizar el servicio.\n\n"
        "⚠️ <b>Importante:</b>\n"
        "El CopyTrading implica riesgo. Las operaciones "
        "pueden generar pérdidas y los resultados anteriores "
        "no garantizan resultados futuros."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="HTML",
    )


# ============================================================
# 📊 MERCADOS
# ============================================================

async def markets_menu(
    query
):

    text = (
        "📊 <b>MERCADOS</b>\n\n"
        "Consulta los principales instrumentos que "
        "seguimos en Apex Quant.\n\n"
        "💱 EUR/USD\n"
        "💱 GBP/USD\n"
        "💱 GBP/JPY\n\n"
        "📌 Nuestro enfoque principal está orientado "
        "al DayTrading.\n\n"
        "⚠️ La información presentada no constituye "
        "asesoramiento financiero."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📅 Calendario económico",
                    callback_data="calendar",
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

    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def show_markets(
    query
):

    await markets_menu(
        query
    )


# ============================================================
# 📡 SEÑALES
# ============================================================

async def signals_menu(
    query
):

    text = (
        "📡 <b>SEÑALES APEX QUANT</b>\n\n"
        "Accede al servicio de señales de trading "
        "de Apex Quant.\n\n"
        "📊 Las señales son preparadas y enviadas "
        "por el administrador.\n\n"
        "💰 <b>Suscripción:</b> 30 USDT / 30 días\n"
        "🌐 <b>Red de pago:</b> BEP20\n\n"
        "⚠️ Las señales no garantizan resultados. "
        "Los mercados financieros implican riesgo "
        "de pérdida de capital.\n\n"
        "👇 Selecciona una opción:"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💳 Suscribirme",
                    callback_data="signal_subscription",
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 Estado de mi suscripción",
                    callback_data="signal_status",
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

    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def show_signals(
    query
):

    await signals_menu(
        query
    )


# ============================================================
# 💳 SUSCRIPCIONES DE SEÑALES
# ============================================================

def load_subscriptions():

    try:

        if not os.path.exists(
            SUBSCRIPTIONS_FILE
        ):
            return {}

        with open(
            SUBSCRIPTIONS_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            dict,
        ):
            return {}

        return data

    except Exception as error:

        logger.error(
            "Error cargando suscripciones: %s",
            error,
        )

        return {}


def save_subscriptions(
    data
):

    try:

        temp_file = (
            f"{SUBSCRIPTIONS_FILE}.tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            temp_file,
            SUBSCRIPTIONS_FILE,
        )

    except Exception as error:

        logger.error(
            "Error guardando suscripciones: %s",
            error,
        )


def is_subscription_active(
    user_id
):

    data = load_subscriptions()

    subscription = data.get(
        str(user_id)
    )

    if not subscription:
        return False

    if not subscription.get(
        "active",
        False,
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

        if expiration <= datetime.utcnow():
            return False

        return True

    except Exception:

        return False


async def show_signal_subscription(
    query
):

    address = USDT_BEP20_ADDRESS

    if address:

        payment_text = (
            "💳 <b>SUSCRIPCIÓN A SEÑALES</b>\n\n"
            f"💰 Precio: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
            f"📅 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
            "🌐 Red: <b>BEP20</b>\n\n"
            "💵 <b>Dirección USDT BEP20:</b>\n"
            f"<code>{address}</code>\n\n"
            "📌 Envía exactamente el importe indicado "
            "a la dirección anterior.\n\n"
            "Después del pago, envía al administrador "
            "el comprobante o hash de la transacción "
            "para verificarlo y activar tu suscripción.\n\n"
            "⚠️ Verifica cuidadosamente la red y la "
            "dirección antes de realizar el envío."
        )

    else:

        payment_text = (
            "💳 <b>SUSCRIPCIÓN A SEÑALES</b>\n\n"
            f"💰 Precio: <b>{SIGNALS_PRICE_USDT} USDT</b>\n"
            f"📅 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
            "🌐 Red: <b>BEP20</b>\n\n"
            "⚠️ La dirección de pago todavía no está "
            "configurada.\n\n"
            "Contacta con el administrador para recibir "
            "las instrucciones de pago."
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📋 Ver mi estado",
                    callback_data="signal_status",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="signals",
                )
            ],
        ]
    )

    await query.edit_message_text(
        text=payment_text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def show_signal_payment(
    query
):

    await show_signal_subscription(
        query
    )


async def show_signal_status(
    query
):

    user_id = query.from_user.id

    active = is_subscription_active(
        user_id
    )

    if active:

        data = load_subscriptions()

        subscription = data.get(
            str(user_id),
            {},
        )

        expires_at = subscription.get(
            "expires_at",
            "",
        )

        text = (
            "🟢 <b>SUSCRIPCIÓN ACTIVA</b>\n\n"
            "📡 Tienes acceso al servicio de "
            "señales de Apex Quant.\n\n"
            "📅 Válida hasta:\n"
            f"<b>{expires_at}</b>\n\n"
            "⚠️ Recuerda que las señales no garantizan "
            "resultados y existe riesgo de pérdida."
        )

    else:

        text = (
            "🔴 <b>SUSCRIPCIÓN INACTIVA</b>\n\n"
            "Actualmente no tienes una suscripción "
            "activa a las señales de Apex Quant.\n\n"
            "💰 Precio: <b>30 USDT / 30 días</b>\n"
            "🌐 Red: <b>BEP20</b>"
        )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💳 Suscribirme",
                        callback_data="signal_subscription",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Volver",
                        callback_data="signals",
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )
