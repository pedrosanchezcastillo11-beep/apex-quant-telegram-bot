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

# ============================================================
# 🛠️ ADMINISTRACIÓN
# ============================================================

def admin_menu():

    return InlineKeyboardMarkup(
        [
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
                    callback_data="admin_subscribers",
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
                    "🔙 Menú principal",
                    callback_data="main_menu",
                )
            ],
        ]
    )


async def show_admin_menu(
    query
):

    if not is_admin(
        query.from_user.id
    ):

        await query.answer(
            "⛔ Acceso no autorizado.",
            show_alert=True,
        )

        return

    text = (
        "🛠️ <b>ADMINISTRACIÓN</b>\n\n"
        "Panel de administración de Apex Quant.\n\n"
        "📡 Enviar señales a suscriptores activos\n"
        "📊 Consultar historial\n"
        "👥 Ver suscriptores\n"
        "📈 Consultar estadísticas\n\n"
        "👇 Selecciona una opción:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=admin_menu(),
        parse_mode="HTML",
    )


async def admin_send_signal(
    query
):

    if not is_admin(
        query.from_user.id
    ):

        await query.answer(
            "⛔ Acceso no autorizado.",
            show_alert=True,
        )

        return

    text = (
        "📡 <b>ENVIAR SEÑAL</b>\n\n"
        "Para enviar una señal a los suscriptores "
        "activos utiliza el comando:\n\n"
        "<code>/signal</code>\n\n"
        "Después del comando escribe el contenido "
        "completo de la señal.\n\n"
        "Ejemplo:\n"
        "<code>/signal EUR/USD\n"
        "Dirección: BUY\n"
        "Entrada: 1.1700\n"
        "SL: 1.1680\n"
        "TP: 1.1760</code>\n\n"
        "📌 La señal será enviada únicamente a los "
        "usuarios con una suscripción activa."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Administración",
                        callback_data="admin_menu",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )


async def admin_signal_history(
    query
):

    if not is_admin(
        query.from_user.id
    ):

        await query.answer(
            "⛔ Acceso no autorizado.",
            show_alert=True,
        )

        return

    text = (
        "📊 <b>HISTORIAL DE SEÑALES</b>\n\n"
        "El historial de señales estará disponible "
        "cuando se hayan enviado las primeras señales "
        "mediante el sistema de administración.\n\n"
        "📌 Esta sección queda preparada para almacenar "
        "y consultar las señales enviadas."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Administración",
                        callback_data="admin_menu",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )


async def admin_subscribers(
    query
):

    if not is_admin(
        query.from_user.id
    ):

        await query.answer(
            "⛔ Acceso no autorizado.",
            show_alert=True,
        )

        return

    data = load_subscriptions()

    active_users = []

    for user_id, subscription in data.items():

        if not isinstance(
            subscription,
            dict,
        ):
            continue

        if not subscription.get(
            "active",
            False,
        ):
            continue

        if is_subscription_active(
            user_id
        ):

            active_users.append(
                user_id
            )

    text = (
        "👥 <b>SUSCRIPTORES ACTIVOS</b>\n\n"
        f"🟢 Suscripciones activas: "
        f"<b>{len(active_users)}</b>\n\n"
    )

    if active_users:

        text += (
            "🆔 <b>Usuarios activos:</b>\n\n"
        )

        for user_id in active_users[:50]:

            text += (
                f"• <code>{user_id}</code>\n"
            )

        if len(active_users) > 50:

            text += (
                "\nℹ️ Se muestran los primeros "
                "50 usuarios."
            )

    else:

        text += (
            "ℹ️ Actualmente no hay suscriptores activos."
        )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Administración",
                        callback_data="admin_menu",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )


async def admin_statistics(
    query
):

    if not is_admin(
        query.from_user.id
    ):

        await query.answer(
            "⛔ Acceso no autorizado.",
            show_alert=True,
        )

        return

    referrals = load_referrals()

    subscriptions = load_subscriptions()

    total_users = len(
        referrals.get(
            "users",
            {},
        )
    )

    total_subscriptions = len(
        subscriptions
    )

    active_subscriptions = 0

    for user_id in subscriptions:

        if is_subscription_active(
            user_id
        ):

            active_subscriptions += 1

    text = (
        "📈 <b>ESTADÍSTICAS</b>\n\n"
        f"👥 Usuarios registrados: "
        f"<b>{total_users}</b>\n"
        f"📡 Suscripciones registradas: "
        f"<b>{total_subscriptions}</b>\n"
        f"🟢 Suscripciones activas: "
        f"<b>{active_subscriptions}</b>\n"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Administración",
                        callback_data="admin_menu",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )


# ============================================================
# 👤 COMANDO /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    register_user(
        user
    )

    if context.args:

        process_referral(
            user,
            context.args[0],
        )

    text = (
        "🔥 <b>Bienvenido a Apex Quant</b>\n\n"
        "Centro de información y herramientas "
        "para mercados financieros.\n\n"
        "📊 <b>Mercados</b>\n"
        "Consulta instrumentos y calendario económico.\n\n"
        "📡 <b>Señales</b>\n"
        "Accede al servicio de señales de Apex Quant.\n\n"
        "📋 <b>CopyTrading</b>\n"
        "Conoce cómo seguir Apex Quant mediante OneRoyal.\n\n"
        "👥 <b>Referidos</b>\n"
        "Invita usuarios y consulta tu estructura "
        "de referidos.\n\n"
        "🏦 <b>OneRoyal</b>\n"
        "Accede a los servicios disponibles mediante "
        "los enlaces de Apex Quant.\n\n"
        "⚠️ <b>Aviso de riesgo</b>\n"
        "El análisis y las señales no garantizan resultados. "
        "Los mercados financieros implican riesgo de pérdida "
        "de capital.\n\n"
        "👇 Selecciona una opción:"
    )

    await update.message.reply_text(
        text=text,
        reply_markup=main_menu(
            user.id
        ),
        parse_mode="HTML",
    )


# ============================================================
# 📡 COMANDO ADMINISTRATIVO /SIGNAL
# ============================================================

async def signal_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(
        user.id
    ):

        await update.message.reply_text(
            "⛔ No tienes autorización para utilizar "
            "este comando."
        )

        return

    if not context.args:

        await update.message.reply_text(
            "📡 <b>ENVIAR SEÑAL</b>\n\n"
            "Escribe la señal después del comando.\n\n"
            "Ejemplo:\n"
            "<code>/signal EUR/USD BUY\n"
            "Entrada: 1.1700\n"
            "SL: 1.1680\n"
            "TP: 1.1760</code>",
            parse_mode="HTML",
        )

        return

    signal_text = " ".join(
        context.args
    )

    subscriptions = load_subscriptions()

    sent = 0
    failed = 0

    for user_id, subscription in subscriptions.items():

        try:

            if not is_subscription_active(
                user_id
            ):
                continue

            await context.bot.send_message(
                chat_id=int(
                    user_id
                ),
                text=(
                    "📡 <b>SEÑAL APEX QUANT</b>\n\n"
                    f"{signal_text}\n\n"
                    "⚠️ Gestiona siempre tu riesgo "
                    "de acuerdo con tu propia operativa."
                ),
                parse_mode="HTML",
            )

            sent += 1

        except Exception as error:

            failed += 1

            logger.error(
                "Error enviando señal a %s: %s",
                user_id,
                error,
            )

    await update.message.reply_text(
        "✅ <b>SEÑAL PROCESADA</b>\n\n"
        f"📡 Enviada a: <b>{sent}</b>\n"
        f"⚠️ No enviada a: <b>{failed}</b>",
        parse_mode="HTML",
    )


# ============================================================
# 💳 ACTIVACIÓN MANUAL DE SUSCRIPCIÓN
# ============================================================

async def activate_subscription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(
        user.id
    ):

        await update.message.reply_text(
            "⛔ No tienes autorización para utilizar "
            "este comando."
        )

        return

    if not context.args:

        await update.message.reply_text(
            "❌ Debes indicar el Telegram ID.\n\n"
            "Ejemplo:\n"
            "<code>/activate 123456789</code>",
            parse_mode="HTML",
        )

        return

    target_id = context.args[0].strip()

    if not target_id.isdigit():

        await update.message.reply_text(
            "❌ El Telegram ID debe contener solamente números."
        )

        return

    subscriptions = load_subscriptions()

    start_time = datetime.utcnow()

    expiration = (
        start_time
        + timedelta(
            days=SIGNALS_DURATION_DAYS
        )
    )

    subscriptions[
        target_id
    ] = {
        "active": True,
        "activated_at": start_time.isoformat(),
        "expires_at": expiration.isoformat(),
        "price_usdt": SIGNALS_PRICE_USDT,
    }

    save_subscriptions(
        subscriptions
    )

    await update.message.reply_text(
        "✅ <b>SUSCRIPCIÓN ACTIVADA</b>\n\n"
        f"🆔 Telegram ID: <code>{target_id}</code>\n"
        f"💰 Precio registrado: "
        f"<b>{SIGNALS_PRICE_USDT} USDT</b>\n"
        f"📅 Duración: <b>{SIGNALS_DURATION_DAYS} días</b>\n"
        f"⏰ Expira: <b>{expiration.isoformat()}</b>",
        parse_mode="HTML",
    )

    try:

        await context.bot.send_message(
            chat_id=int(
                target_id
            ),
            text=(
                "🎉 <b>¡SUSCRIPCIÓN ACTIVADA!</b>\n\n"
                "📡 Tu suscripción a las señales "
                "de Apex Quant está activa.\n\n"
                f"📅 Válida durante "
                f"<b>{SIGNALS_DURATION_DAYS} días</b>.\n\n"
                "⚠️ Las señales no garantizan resultados "
                "y los mercados financieros implican riesgo."
            ),
            parse_mode="HTML",
        )

    except Exception as error:

        logger.error(
            "No se pudo notificar activación a %s: %s",
            target_id,
            error,
        )


# ============================================================
# 🔘 MANEJADOR PRINCIPAL DE BOTONES
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data

    # --------------------------------------------------------
    # MENÚ PRINCIPAL
    # --------------------------------------------------------

    if data == "main_menu":

        await query.edit_message_text(
            text=(
                "🔥 <b>APEX QUANT</b>\n\n"
                "Selecciona una opción:"
            ),
            reply_markup=main_menu(
                query.from_user.id
            ),
            parse_mode="HTML",
        )

        return

    # --------------------------------------------------------
    # MERCADOS
    # --------------------------------------------------------

    if data == "markets":

        await show_markets(
            query
        )

        return

    # --------------------------------------------------------
    # SEÑALES
    # --------------------------------------------------------

    if data == "signals":

        await show_signals(
            query
        )

        return

    if data == "signal_subscription":

        await show_signal_subscription(
            query
        )

        return

    if data == "signal_payment":

        await show_signal_payment(
            query
        )

        return

    if data == "signal_status":

        await show_signal_status(
            query
        )

        return

    # --------------------------------------------------------
    # COPYTRADING
    # --------------------------------------------------------

    if data == "copytrading":

        await show_copy_info(
            query
        )

        return

    if data == "copy_info":

        await show_copy_info(
            query
        )

        return

    if data == "copy_follow":

        await show_copy_follow(
            query
        )

        return

    if data == "copy_register":

        await show_copy_register(
            query
        )

        return

    if data == "copy_steps":

        await show_copy_steps(
            query
        )

        return

    # --------------------------------------------------------
    # REFERIDOS
    # --------------------------------------------------------

    if data == "referrals":

        await show_referrals(
            query
        )

        return

    if data == "referral_link":

        await show_referral_link(
            query
        )

        return

    if data == "referral_stats":

        await show_referral_stats(
            query
        )

        return

    if data == "referral_commissions":

        await show_referral_commissions(
            query
        )

        return

    # --------------------------------------------------------
    # CALENDARIO
    # --------------------------------------------------------

    if data == "calendar":

        await show_calendar(
            query
        )

        return

    if data == "calendar_today":

        await show_calendar_today(
            query
        )

        return

    if data == "calendar_tomorrow":

        await show_calendar_tomorrow(
            query
        )

        return

    if data == "calendar_week":

        await show_calendar_week(
            query
        )

        return

    if data == "calendar_high":

        await show_calendar_high(
            query
        )

        return

    if data == "calendar_currency":

        await currency_events(
            query
        )

        return

    if data.startswith(
        "currency_"
    ):

        currency = data.split(
            "_",
            1,
        )[1]

        await show_currency_events(
            query,
            currency,
        )

        return

    # --------------------------------------------------------
    # IDIOMA
    # --------------------------------------------------------

    if data == "language":

        await show_language(
            query
        )

        return

    if data == "language_es":

        await set_language(
            query,
            "es",
        )

        return

    if data == "language_en":

        await set_language(
            query,
            "en",
        )

        return

    # --------------------------------------------------------
    # CONFIGURACIÓN
    # --------------------------------------------------------

    if data == "settings":

        await show_settings(
            query
        )

        return

    # --------------------------------------------------------
    # ADMINISTRACIÓN
    # --------------------------------------------------------

    if data == "admin_menu":

        await show_admin_menu(
            query
        )

        return

    if data == "admin_send_signal":

        await admin_send_signal(
            query
        )

        return

    if data == "admin_signal_history":

        await admin_signal_history(
            query
        )

        return

    if data == "admin_subscribers":

        await admin_subscribers(
            query
        )

        return

    if data == "admin_statistics":

        await admin_statistics(
            query
        )

        return

    # --------------------------------------------------------
    # CALLBACK DESCONOCIDO
    # --------------------------------------------------------

    await query.edit_message_text(
        text=(
            "⚠️ <b>Opción no disponible</b>\n\n"
            "Esta función todavía no está disponible."
        ),
        reply_markup=back_main_menu(),
        parse_mode="HTML",
    )


# ============================================================
# 🚨 MANEJADOR DE ERRORES
# ============================================================

async def error_handler(
    update,
    context,
):

    logger.error(
        "Exception while handling an update:",
        exc_info=context.error,
    )


# ============================================================
# 🚀 INICIO DEL BOT
# ============================================================

def main():

    application = (
        Application.builder()
        .token(
            BOT_TOKEN
        )
        .build()
    )

    # --------------------------------------------------------
    # COMANDOS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "signal",
            signal_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "activate",
            activate_subscription,
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

    logger.info(
        "🔥 Apex Quant Bot iniciado correctamente."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()
