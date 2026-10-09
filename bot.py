# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import json
import io
import hashlib
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from html import escape
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from datetime import datetime, timedelta, date, timezone

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
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
CONSENTS_FILE = os.getenv("CONSENTS_FILE", "/data/consents.json").strip()

# ============================================================
# ASISTENTE IA APEXQUANT — GEMMA 4 + BÚSQUEDA WEB HÍBRIDA
# ============================================================
# Gemma 4 genera la respuesta final. Gemini se conserva únicamente
# como motor de búsqueda web cuando la pregunta necesita información reciente.
# Esto permite usar Gemma 4 sin perder la función de búsqueda web existente.
def _clean_key(value):
    """Limpia espacios y comillas (rectas o curvas) que se cuelan al pegar la key en Deployka."""
    return (value or "").strip().strip('"').strip("'").strip("\u201d").strip("\u201c").strip()

GEMMA_API_KEY = _clean_key(os.getenv("GEMMA_API_KEY") or os.getenv("GEMINI_API_KEY"))
logger.info("GEMMA key cargada: len=%s, inicio=%s", len(GEMMA_API_KEY), GEMMA_API_KEY[:3])
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it").strip()
GEMMA_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Búsqueda web opcional mediante Gemini. Puede utilizar la misma API key.
GEMINI_SEARCH_API_KEY = _clean_key(os.getenv("GEMINI_SEARCH_API_KEY") or os.getenv("GEMINI_API_KEY"))
GEMINI_SEARCH_MODEL = os.getenv("GEMINI_SEARCH_MODEL", "gemini-2.5-flash").strip()
GEMINI_WEB_SEARCH = os.getenv("GEMINI_WEB_SEARCH", "true").strip().lower() in {"1", "true", "yes", "on"}

ASSISTANT_MAX_HISTORY = 8
ASSISTANT_MAX_OUTPUT = 1800
# Gemma 4 "piensa" antes de responder y esos tokens cuentan contra el límite.
# Se deja margen extra para que el razonamiento no se coma la respuesta visible.
ASSISTANT_THINKING_HEADROOM = 3000
ASSISTANT_WEB_CONTEXT_MAX = 5000

# ============================================================
# ONEROYAL
# ============================================================

ONEROYAL_IB_URL = os.getenv("ONEROYAL_IB_LINK", os.getenv("ONEROYAL_IB_URL", "")).strip()
ONEROYAL_COPYTRADING_URL = os.getenv(
    "ONEROYAL_COPYTRADING_LINK",
    os.getenv(
        "ONEROYAL_COPYTRADING_URL",
        "https://socialtrading.oneroyal.com/portal/registration/subscription/82924/ApexQuant95"
    )
).strip()

# Oferta de CopyTrading de ApexQuant. El enlace completo es la referencia
# operativa; 82924 es el identificador visible de la oferta en la URL.
APEXQUANT_OFFER_ID = "82924"
APEXQUANT_OFFER_NAME = "ApexQuant95"

# ============================================================
# ACADEMIA
# ============================================================

ACADEMY_NAME = "Academia Apex Quant"

# ============================================================
# FINANCE CALENDAR
# ============================================================

FINANCE_CALENDAR_BASE = (
    "https://www.financecalendar.com/wp-json/fc/v1"
)

# ============================================================
# COMUNIDAD APEXQUANT
# ============================================================

COMMUNITY_INVITE_URL = os.getenv("COMMUNITY_INVITE_URL", "https://t.me/+FS_bDcUdF4AyOTFh").strip()
COMMUNITY_CHANNEL_ID = os.getenv("COMMUNITY_CHANNEL_ID", "").strip()
COMMUNITY_CONFIG_FILE = os.getenv("COMMUNITY_CONFIG_FILE", "/data/community_config.json").strip()
COMMUNITY_STATS_FILE = os.getenv("COMMUNITY_STATS_FILE", "/data/community_stats.json").strip()
COMMUNITY_EVENTS_FILE = os.getenv("COMMUNITY_EVENTS_FILE", "/data/community_events.json").strip()

# Enlaces oficiales de las redes sociales de ApexQuant.
# Los valores predeterminados permiten que el bot funcione aunque no se creen ENV.
FACEBOOK_URL = os.getenv("FACEBOOK_URL", "https://www.facebook.com/share/1PATSc2Gxv/").strip()
TWITTER_URL = os.getenv("TWITTER_URL", "https://x.com/ApexQuant_Fx").strip()
YOUTUBE_URL = os.getenv("YOUTUBE_URL", "https://youtube.com/@apexquantfx?si=xnYPtmYxDfsSUYcr").strip()

COMMUNITY_DAILY_TARGET = 3
HIGH_IMPACT_CHECK_SECONDS = 300

# ============================================================
# FUNCIONES GENERALES
# ============================================================

def is_admin(user_id):
    """Comprueba si el usuario es administrador."""
    return str(user_id) == str(ADMIN_TELEGRAM_ID)


# ============================================================
# MENÚ PRINCIPAL
# ============================================================

def main_menu(user_id=None):
    keyboard = [
        [
            InlineKeyboardButton("📊 Mercados", callback_data="markets"),
            InlineKeyboardButton("📋 CopyTrading", callback_data="copytrading")
        ],
        [
            InlineKeyboardButton("👥 Referidos", callback_data="referrals"),
            InlineKeyboardButton("🎓 Academia", callback_data="academy")
        ],
        [
            InlineKeyboardButton("🌐 Comunidad", callback_data="community")
        ],
        [
            InlineKeyboardButton("🤖 Asistente ApexQuant", callback_data="assistant")
        ],
        [
            InlineKeyboardButton("🟢 Broker OneRoyal", callback_data="broker_oneroyal")
        ],
        [
            InlineKeyboardButton("🌐 Idioma", callback_data="language"),
            InlineKeyboardButton("⚙️ Configuración", callback_data="settings")
        ]
    ]
    if user_id is not None and is_admin(user_id):
        keyboard.append([InlineKeyboardButton("🛠️ Administración", callback_data="admin_menu")])
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# COMUNIDAD — CONFIGURACIÓN Y ACCESO
# ============================================================

def _load_json_file(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as error:
        logger.error("Error leyendo %s: %s", path, error)
        return default


def _save_json_file(path, data):
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
        return True
    except Exception as error:
        logger.error("Error guardando %s: %s", path, error)
        return False


def get_community_channel_id():
    if COMMUNITY_CHANNEL_ID:
        return COMMUNITY_CHANNEL_ID
    data = _load_json_file(COMMUNITY_CONFIG_FILE, {})
    return str(data.get("channel_id", "")).strip()


def save_community_channel_id(channel_id, title=""):
    return _save_json_file(COMMUNITY_CONFIG_FILE, {"channel_id": str(channel_id), "title": title, "updated_at": datetime.utcnow().isoformat() + "Z"})


def _today_key():
    return date.today().isoformat()


def community_post_count():
    data = _load_json_file(COMMUNITY_STATS_FILE, {})
    return int(data.get(_today_key(), 0) or 0)


def register_community_post():
    data = _load_json_file(COMMUNITY_STATS_FILE, {})
    key = _today_key()
    data[key] = int(data.get(key, 0) or 0) + 1
    for old_key in sorted(list(data))[:-14]:
        data.pop(old_key, None)
    _save_json_file(COMMUNITY_STATS_FILE, data)
    return data[key]


async def is_community_member(bot, user_id):
    channel_id = get_community_channel_id()
    if not channel_id:
        return None
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        status = str(getattr(member, "status", "")).lower()
        if status in {"member", "administrator", "creator"}:
            return True
        if status == "restricted" and bool(getattr(member, "is_member", False)):
            return True
        return False
    except Exception as error:
        logger.error("Error verificando membresía en Comunidad: %s", error)
        return False


async def show_community_gate(query):
    text = (
        "🌐 <b>COMUNIDAD APEXQUANT</b>\n\n"
        "Para acceder al bot debes formar parte de la comunidad oficial de ApexQuant.\n\n"
        "1️⃣ Pulsa <b>📢 Unirme al canal</b>.\n"
        "2️⃣ Únete al canal oficial.\n"
        "3️⃣ Regresa y pulsa <b>✅ Verificar acceso</b>.\n\n"
        "⚠️ El acceso al menú principal se habilita después de verificar tu membresía."
    )
    keyboard = [
        [InlineKeyboardButton("📢 Unirme al canal", url=COMMUNITY_INVITE_URL)],
        [InlineKeyboardButton("✅ Verificar acceso", callback_data="community_verify")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_community(query):
    text = (
        "🌐 <b>COMUNIDAD APEXQUANT</b>\n\n"
        "Conéctate con ApexQuant en nuestras redes oficiales.\n\n"
        "📢 Telegram — canal oficial y novedades de la comunidad.\n"
        "📘 Facebook — publicaciones y noticias de ApexQuant.\n"
        "𝕏 X (Twitter) — actualizaciones y contenido de mercado.\n"
        "▶️ YouTube — contenido audiovisual de ApexQuant.\n\n"
        "💚 <b>Aprende, sigue y crece con nosotros.</b>"
    )
    keyboard = [
        [InlineKeyboardButton("📢 Canal de Telegram", url=COMMUNITY_INVITE_URL)],
        [InlineKeyboardButton("📘 Facebook", url=FACEBOOK_URL),
         InlineKeyboardButton("𝕏 X (Twitter)", url=TWITTER_URL)],
        [InlineKeyboardButton("▶️ YouTube", url=YOUTUBE_URL)],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]
    ]
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )


async def capture_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post:
        return
    chat = post.chat
    save_community_channel_id(chat.id, getattr(chat, "title", ""))
    logger.info("Canal de Comunidad detectado: %s (%s)", chat.id, getattr(chat, "title", ""))


async def verify_community_access(query):
    result = await is_community_member(query.get_bot(), query.from_user.id)
    if result is True:
        await query.edit_message_text("✅ <b>ACCESO VERIFICADO</b>\n\nTu membresía en la Comunidad ApexQuant ha sido confirmada.", parse_mode="HTML", reply_markup=main_menu(query.from_user.id))
        return
    if result is None:
        await query.edit_message_text("⏳ <b>CANAL PENDIENTE DE DETECCIÓN</b>\n\nEl bot todavía no ha recibido ninguna publicación del canal oficial. El administrador debe publicar un mensaje en el canal una vez después del despliegue para que ApexQuant pueda identificarlo automáticamente.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Canal de Telegram", url=COMMUNITY_INVITE_URL)],
            [InlineKeyboardButton("🔄 Verificar nuevamente", callback_data="community_verify")]
        ]))
        return
    await query.edit_message_text("❌ <b>NO SE HA VERIFICADO TU MEMBRESÍA</b>\n\nÚnete al canal oficial y vuelve a pulsar <b>✅ Verificar acceso</b>.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Unirme al canal", url=COMMUNITY_INVITE_URL)],
        [InlineKeyboardButton("🔄 Verificar acceso", callback_data="community_verify")]
    ]))


# ============================================================
# COPYTRADING
# ============================================================

def copytrading_menu():

    keyboard = []

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
        "💰 <b>Comisión de rendimiento:</b>\n"
        "ApexQuant no cobra cuota de entrada ni cuota fija de gestión. "
        "La comisión se aplica sobre las ganancias generadas de acuerdo con "
        "las condiciones de la oferta. Si no se generan ganancias sujetas "
        "a comisión, no se genera comisión de rendimiento.\n\n"
        "🌎 <b>Elegibilidad:</b> OneRoyal aplica restricciones por jurisdicción. "
        "Comprueba que puedes utilizar sus servicios desde tu país antes de "
        "registrarte o depositar fondos.\n\n"
        "⚠️ <b>Importante:</b>\n"
        "El CopyTrading implica riesgo. Los resultados pasados no garantizan "
        "resultados futuros y puedes perder capital.\n\n"
        "👇 <b>Cómo empezar:</b>\n"
        "1️⃣ Pulsa <b>🏦 Abrir cuenta OneRoyal</b> para registrarte.\n"
        "2️⃣ Después pulsa <b>📈 Seguir Apex Quant</b> para conectarte al CopyTrading."
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
        "de riesgo que utilice.\n\n"
        "💰 <b>Comisiones:</b> ApexQuant no cobra cuota de entrada ni cuota fija "
        "de gestión. La comisión de rendimiento, si corresponde, se aplica según "
        "las condiciones vigentes de la oferta. Si no hay ganancias sujetas a "
        "comisión, no hay comisión de rendimiento.\n\n"
        "🌎 <b>Elegibilidad regional:</b> verifica tu país antes de registrarte. "
        "OneRoyal mantiene restricciones regionales y sus condiciones pueden variar."
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


def event_currency(event):
    """Obtiene la divisa afectada de forma robusta.

    FinanceCalendar no garantiza un campo `currency` en todos sus eventos.
    Por eso probamos primero códigos directos y, si no existen, usamos país,
    nombre/título y la URL del evento como respaldo.
    """

    if not isinstance(event, dict):
        return ""

    # 1) Campos directos que distintas versiones/feeds pueden entregar.
    direct_keys = (
        "currency",
        "currency_code",
        "currencyCode",
        "ccy",
        "currency_iso",
        "currencyIso",
        "currency_iso_code",
        "currencyIsoCode",
    )

    for key in direct_keys:
        value = event.get(key)

        if isinstance(value, dict):
            value = (
                value.get("code")
                or value.get("currency")
                or value.get("iso")
                or value.get("iso_code")
                or value.get("isoCode")
            )

        if value is not None:
            code = str(value).upper().strip()
            if code in {
                "USD", "EUR", "GBP", "JPY", "CHF", "CAD",
                "AUD", "NZD", "CNY", "CNH", "HKD", "SGD", "SEK",
                "NOK", "DKK", "MXN", "BRL", "INR", "KRW", "ZAR"
            }:
                return code

    # 2) País/código de país.
    country = event_value(
        event,
        "countryCode",
        "country_code",
        "country",
        "countryName",
        "country_name"
    )

    country_text = str(country or "").upper().strip()

    country_map = {
        "US": "USD", "USA": "USD", "UNITED STATES": "USD",
        "EU": "EUR", "EUROZONE": "EUR", "EURO AREA": "EUR",
        "GERMANY": "EUR", "FRANCE": "EUR", "ITALY": "EUR",
        "SPAIN": "EUR", "NETHERLANDS": "EUR",
        "GB": "GBP", "UK": "GBP", "UNITED KINGDOM": "GBP",
        "JAPAN": "JPY", "JP": "JPY",
        "SWITZERLAND": "CHF", "CH": "CHF",
        "CANADA": "CAD", "CA": "CAD",
        "AUSTRALIA": "AUD", "AU": "AUD",
        "NEW ZEALAND": "NZD", "NZ": "NZD",
        "CHINA": "CNY", "CN": "CNY",
        "HONG KONG": "HKD", "HK": "HKD",
        "SINGAPORE": "SGD", "SG": "SGD",
        "SWEDEN": "SEK", "SE": "SEK",
        "NORWAY": "NOK", "NO": "NOK",
        "DENMARK": "DKK", "DK": "DKK",
        "MEXICO": "MXN", "MX": "MXN",
        "BRAZIL": "BRL", "BR": "BRL",
        "INDIA": "INR", "IN": "INR",
        "SOUTH KOREA": "KRW", "KOREA": "KRW", "KR": "KRW",
        "SOUTH AFRICA": "ZAR", "ZA": "ZAR",
    }

    if country_text in country_map:
        return country_map[country_text]

    # 3) País/divisa implícito en el nombre, título o URL.
    name = str(
        event_value(event, "name", "title", "event")
        or ""
    ).upper()
    url = str(event_value(event, "url", "link") or "").upper()
    haystack = f"{name} {url}"

    keyword_map = [
        (("US ", "U.S.", "UNITED STATES", "AMERICAN", "FED", "FOMC",
          "FEDERAL RESERVE", "JOBLESS CLAIM", "NON-FARM", "NONFARM",
          "PAYROLL", "ADP EMPLOYMENT", "ISM ", "US CPI", "US GDP",
          "US RETAIL", "BEIGE BOOK"), "USD"),
        (("EUROZONE", "EURO AREA", "EUROPEAN CENTRAL BANK", "ECB",
          "EUROPEAN", "GERMANY", "FRANCE", "ITALY", "SPAIN"), "EUR"),
        (("UK ", "U.K.", "UNITED KINGDOM", "BRITAIN", "BOE",
          "BANK OF ENGLAND", "BRITISH"), "GBP"),
        (("JAPAN", "BOJ", "BANK OF JAPAN", "JAPANESE"), "JPY"),
        (("SWITZERLAND", "SNB", "SWISS NATIONAL BANK", "SWISS"), "CHF"),
        (("CANADA", "BOC", "BANK OF CANADA", "CANADIAN"), "CAD"),
        (("AUSTRALIA", "RBA", "RESERVE BANK OF AUSTRALIA", "AUSTRALIAN"), "AUD"),
        (("NEW ZEALAND", "RBNZ", "RESERVE BANK OF NEW ZEALAND", "NEW ZEALAND"), "NZD"),
        (("CHINA", "PBOC", "PEOPLE'S BANK OF CHINA", "CHINESE"), "CNY"),
    ]

    for keywords, code in keyword_map:
        if any(keyword in haystack for keyword in keywords):
            return code

    return ""


# ============================================================
# CONTEXTO DINÁMICO DE EVENTOS
# ============================================================

CALENDAR_EVENT_CACHE = {}
CALENDAR_WEB_CONTEXT_CACHE = {}


def calendar_event_key(event):

    raw = "|".join(
        str(event_value(event, key))
        for key in (
            "id",
            "event_id",
            "name",
            "title",
            "currency",
            "date",
            "datetime",
            "time_utc"
        )
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:10]


def cache_calendar_event(event):

    key = calendar_event_key(event)
    CALENDAR_EVENT_CACHE[key] = event

    if len(CALENDAR_EVENT_CACHE) > 100:
        oldest_key = next(iter(CALENDAR_EVENT_CACHE))
        CALENDAR_EVENT_CACHE.pop(oldest_key, None)

    return key


def calendar_event_profile(name):
    """Perfil educativo base según el tipo de evento."""

    text = str(name or "").lower()

    profile = {
        "measure": "Indicador económico programado.",
        "why": (
            "Su importancia depende del resultado, las expectativas "
            "previas y el contexto económico."
        ),
        "higher": (
            "Un resultado superior al esperado puede modificar las "
            "expectativas del mercado sobre crecimiento, inflación "
            "o política monetaria."
        ),
        "lower": (
            "Un resultado inferior al esperado puede modificar las "
            "expectativas del mercado sobre crecimiento, inflación "
            "o política monetaria."
        )
    }

    if any(x in text for x in (
        "cpi", "consumer price", "inflation"
    )):
        profile = {
            "measure": (
                "Mide la evolución de los precios que pagan los consumidores "
                "y ayuda a evaluar las presiones inflacionarias."
            ),
            "why": (
                "La inflación es especialmente relevante para las expectativas "
                "sobre las decisiones de los bancos centrales."
            ),
            "higher": (
                "Una inflación superior a la esperada puede aumentar las "
                "expectativas de una política monetaria más restrictiva."
            ),
            "lower": (
                "Una inflación inferior a la esperada puede reducir las "
                "expectativas de presión monetaria."
            )
        }

    elif any(x in text for x in (
        "nfp", "non-farm", "employment situation", "payroll",
        "adp employment"
    )):
        profile = {
            "measure": (
                "Evalúa la evolución del mercado laboral, incluyendo la "
                "creación de empleo según el informe correspondiente."
            ),
            "why": (
                "El empleo ayuda a evaluar la fortaleza de la economía y "
                "las expectativas de política monetaria."
            ),
            "higher": (
                "Un resultado laboral más fuerte de lo esperado puede "
                "reforzar la percepción de una economía resistente."
            ),
            "lower": (
                "Un resultado laboral más débil puede aumentar las "
                "expectativas de una economía menos resistente."
            )
        }

    elif any(x in text for x in (
        "jobless", "unemployment", "labour force", "labor force"
    )):
        profile = {
            "measure": (
                "Proporciona información sobre las condiciones del mercado "
                "laboral y el nivel de empleo o desempleo."
            ),
            "why": (
                "El mercado laboral es uno de los factores considerados por "
                "los bancos centrales al evaluar la economía."
            ),
            "higher": (
                "Una mejora del empleo o una caída del desempleo puede "
                "interpretarse como mayor fortaleza laboral."
            ),
            "lower": (
                "Un deterioro del empleo o un aumento del desempleo puede "
                "señalar una pérdida de fortaleza laboral."
            )
        }

    elif any(x in text for x in (
        "pmi", "ism manufacturing", "ism services"
    )):
        profile = {
            "measure": (
                "Mide la actividad empresarial y ayuda a evaluar si "
                "determinados sectores se expanden o contraen."
            ),
            "why": (
                "Puede ofrecer una señal relativamente temprana sobre "
                "la actividad económica."
            ),
            "higher": "Un resultado superior al esperado suele indicar mayor actividad económica.",
            "lower": "Un resultado inferior al esperado puede señalar una pérdida de actividad económica."
        }

    elif any(x in text for x in (
        "gdp", "gross domestic product"
    )):
        profile = {
            "measure": "Mide el crecimiento de la producción económica de un país o región.",
            "why": "Permite evaluar la fortaleza general de la economía.",
            "higher": "Un crecimiento superior al esperado puede reforzar la percepción de una economía más sólida.",
            "lower": "Un crecimiento inferior al esperado puede generar preocupación sobre la actividad económica."
        }

    elif any(x in text for x in (
        "retail sales", "consumer spending", "personal income"
    )):
        profile = {
            "measure": "Aporta información sobre el consumo y los ingresos de los hogares.",
            "why": "El consumo representa una parte importante de la actividad económica.",
            "higher": "Un consumo superior al esperado puede apuntar a una demanda interna más resistente.",
            "lower": "Un consumo inferior al esperado puede apuntar a una demanda más débil."
        }

    elif any(x in text for x in (
        "ppi", "producer price"
    )):
        profile = {
            "measure": "Mide cambios en los precios recibidos por productores y aporta información sobre presiones de costes.",
            "why": "Puede ofrecer información adicional sobre la evolución de las presiones inflacionarias.",
            "higher": "Un dato superior puede sugerir mayores presiones de costes.",
            "lower": "Un dato inferior puede indicar menores presiones de costes."
        }

    elif any(x in text for x in (
        "fomc", "fed", "federal reserve", "ecb", "bank of england",
        "boe", "bank of japan", "boj", "bank of canada", "boc",
        "rba", "rbnz", "snb", "rate decision", "interest rate"
    )):
        profile = {
            "measure": "Es un evento relacionado con política monetaria o comunicación de un banco central.",
            "why": "Los tipos de interés y la orientación monetaria pueden modificar las expectativas sobre el coste del dinero.",
            "higher": "Un tono más restrictivo de lo esperado puede aumentar las expectativas de tipos más elevados.",
            "lower": "Un tono más flexible de lo esperado puede reducir las expectativas de tipos elevados."
        }

    elif any(x in text for x in (
        "minutes", "beige book"
    )):
        profile = {
            "measure": "Recoge información y opiniones sobre las condiciones económicas y, en algunos casos, el debate de política monetaria.",
            "why": "Puede ayudar a interpretar cómo evolucionan las expectativas sobre futuras decisiones monetarias.",
            "higher": "Un tono más restrictivo puede reforzar las expectativas de una política monetaria más firme.",
            "lower": "Un tono más flexible puede reducir esas expectativas."
        }

    elif any(x in text for x in (
        "consumer confidence", "consumer sentiment"
    )):
        profile = {
            "measure": "Evalúa la percepción de los consumidores sobre la economía y sus condiciones futuras.",
            "why": "La confianza puede influir en las expectativas sobre consumo y actividad económica.",
            "higher": "Una confianza superior puede indicar una percepción más positiva de la economía.",
            "lower": "Una confianza inferior puede señalar mayor cautela entre los consumidores."
        }

    elif any(x in text for x in (
        "housing", "home sales"
    )):
        profile = {
            "measure": "Proporciona información sobre la actividad del mercado inmobiliario.",
            "why": "La vivienda está relacionada con consumo, crédito y actividad económica.",
            "higher": "Una actividad inmobiliaria mayor puede reforzar la percepción de demanda resistente.",
            "lower": "Una actividad menor puede señalar debilidad en determinados segmentos."
        }

    elif "trade balance" in text:
        profile = {
            "measure": "Mide la diferencia entre exportaciones e importaciones de bienes y servicios.",
            "why": "Permite evaluar parte de la relación comercial de una economía con el exterior.",
            "higher": "Un saldo comercial más favorable puede reflejar una mejora relativa de las exportaciones.",
            "lower": "Un saldo menos favorable puede reflejar mayores importaciones o menores exportaciones."
        }

    return profile


def affected_currencies(currency, name=""):
    currency = str(currency or "").upper()
    text = str(name or "").lower()

    direct = {
        "USD": ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"],
        "EUR": ["EUR", "USD", "GBP", "CHF"],
        "GBP": ["GBP", "USD", "EUR"],
        "JPY": ["JPY", "USD", "AUD"],
        "CHF": ["CHF", "USD", "EUR"],
        "CAD": ["CAD", "USD"],
        "AUD": ["AUD", "USD", "JPY"],
        "NZD": ["NZD", "USD", "AUD"]
    }

    # Eventos de bancos centrales suelen afectar principalmente a su divisa.
    central_bank = any(x in text for x in (
        "fomc", "fed", "federal reserve", "ecb", "bank of england",
        "boe", "bank of japan", "boj", "bank of canada", "boc",
        "rba", "rbnz", "snb"
    ))

    if central_bank and currency:
        related = direct.get(currency, [currency])
        return related[:5]

    return direct.get(
        currency,
        [currency] if currency else []
    )


async def fetch_web_headlines(event):
    """Busca contexto reciente bajo demanda mediante Google News RSS."""

    name = str(event_value(event, "name", "title", "event") or "economic event")
    currency = event_currency(event)
    cache_key = calendar_event_key(event)

    cached = CALENDAR_WEB_CONTEXT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    query_text = f'"{name}" {currency} economy' if currency else f'"{name}" economy'

    url = (
        "https://news.google.com/rss/search?"
        + urlencode({
            "q": query_text,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en"
        })
    )

    def load_news():
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 ApexQuantBot/1.0"
            }
        )
        with urlopen(request, timeout=10) as response:
            return response.read()

    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, load_news)
        root = ET.fromstring(raw)
        headlines = []

        for item in root.findall(".//item")[:4]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            source = item.findtext("source", "").strip()

            if title:
                headlines.append({
                    "title": title,
                    "link": link,
                    "source": source
                })

        CALENDAR_WEB_CONTEXT_CACHE[cache_key] = headlines
        if len(CALENDAR_WEB_CONTEXT_CACHE) > 50:
            oldest_key = next(iter(CALENDAR_WEB_CONTEXT_CACHE))
            CALENDAR_WEB_CONTEXT_CACHE.pop(oldest_key, None)

        return headlines

    except Exception as error:
        logger.warning(
            "No se pudo obtener contexto web para %s: %s",
            name,
            error
        )
        return []


def event_result_interpretation(consensus, prior, actual):

    if not actual:
        return (
            "⏳ <b>Lectura actual:</b> el dato todavía no ha sido publicado. "
            "El consenso y el dato anterior sirven como referencias para comparar "
            "el resultado cuando se publique."
        )

    if not consensus:
        return (
            "🧾 <b>Lectura actual:</b> el dato ya fue publicado, pero no hay "
            "consenso disponible para una comparación directa."
        )

    return (
        "📌 <b>Lectura actual:</b> compara el resultado con el consenso y el "
        "dato anterior. La reacción del mercado también depende de las "
        "expectativas previas y del contexto macroeconómico."
    )


async def show_calendar_context(query, event_key):

    event = CALENDAR_EVENT_CACHE.get(event_key)

    if not event:
        await query.edit_message_text(
            "⚠️ <b>El contexto de este evento ya no está disponible.</b>\n\n"
            "Actualiza el calendario y vuelve a seleccionar el evento.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Actualizar", callback_data="calendar")
            ]])
        )
        return

    name = str(event_value(event, "name", "title", "event") or "Evento económico")
    currency = event_currency(event) or "N/D"
    impact = str(event_value(event, "impact", "importance") or "N/D").lower()
    consensus = event_value(event, "consensus", "forecast", "expected")
    prior = event_value(event, "prior", "previous")
    actual = event_value(event, "actual")

    profile = calendar_event_profile(name)
    affected = affected_currencies(currency, name)
    headlines = await fetch_web_headlines(event)

    impact_text = {
        "high": "🔴 ALTO",
        "medium": "🟠 MEDIO",
        "low": "🟢 BAJO"
    }.get(impact, "⚪ N/D")

    lines = [
        "📚 <b>CONTEXTO DEL EVENTO</b>",
        "",
        f"📰 <b>{escape(name)}</b>",
        f"🌎 Divisa principal: <b>{escape(currency)}</b>",
        f"📊 Impacto: <b>{impact_text}</b>",
        "",
        "📖 <b>¿Qué es?</b>",
        escape(profile["measure"]),
        "",
        "🏦 <b>¿Por qué importa?</b>",
        escape(profile["why"]),
        "",
        "📈 <b>Si sorprende al alza:</b>",
        escape(profile["higher"]),
        "",
        "📉 <b>Si sorprende a la baja:</b>",
        escape(profile["lower"]),
        "",
        "💱 <b>Posibles divisas afectadas:</b>",
        escape(", ".join(affected) or "N/D"),
        "",
        event_result_interpretation(consensus, prior, actual)
    ]

    keyboard = []

    if headlines:
        lines.extend([
            "",
            "🌐 <b>Información reciente encontrada en la web:</b>"
        ])

        for index, item in enumerate(headlines[:4], start=1):
            source = f" — {item['source']}" if item.get("source") else ""
            lines.append(
                f"• {escape(item['title'])}{escape(source)}"
            )
            if item.get("link"):
                keyboard.append([
                    InlineKeyboardButton(
                        f"📰 Fuente {index}",
                        url=item["link"]
                    )
                ])
    else:
        lines.extend([
            "",
            "🌐 <b>Información web:</b>",
            "No se encontraron titulares recientes relacionados "
            "de forma suficientemente clara con este evento."
        ])

    lines.extend([
        "",
        "⚠️ <b>ApexQuant:</b> este contexto es informativo y educativo. "
        "No constituye una predicción garantizada ni una señal de compra o venta.",
        "",
        "ℹ️ Datos del calendario: FinanceCalendar.com"
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Volver al calendario",
            callback_data="calendar"
        )
    ])

    await query.edit_message_text(
        "\n".join(lines)[:3900],
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# FORMATEAR EVENTO
# ============================================================

def format_calendar_event(event):

    name = event_value(event, "name", "title", "event")
    currency = event_currency(event)
    impact = event_value(event, "impact", "importance")
    event_date = event_value(event, "date", "datetime", "time_utc", "time_et")
    consensus = event_value(event, "consensus", "forecast", "expected")
    prior = event_value(event, "prior", "previous")
    actual = event_value(event, "actual")

    impact_text = str(impact).lower()
    if impact_text == "high":
        impact_icon, impact_label = "🔴", "ALTO"
    elif impact_text == "medium":
        impact_icon, impact_label = "🟠", "MEDIO"
    elif impact_text == "low":
        impact_icon, impact_label = "🟢", "BAJO"
    else:
        impact_icon = "⚪"
        impact_label = str(impact) if impact else "N/D"

    currency_text = str(currency).upper() if currency else "N/D"
    event_date_text = str(event_date).replace("T", " ") if event_date else "Hora no disponible"

    result_lines = []
    if consensus:
        result_lines.append(f"📊 Consenso: {escape(str(consensus))}")
    if prior:
        result_lines.append(f"⏮️ Anterior: {escape(str(prior))}")
    if actual:
        result_lines.append(f"✅ Actual: {escape(str(actual))}")

    result_text = "\n" + "\n".join(result_lines) if result_lines else ""

    return (
        f"{impact_icon} <b>{escape(impact_label)}</b> | <b>{escape(currency_text)}</b>\n"
        f"📰 {escape(str(name or 'Evento económico'))}\n"
        f"🕒 {escape(event_date_text)}"
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

            event_currency_code = event_currency(event)

            if event_currency_code != currency.upper():
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
    # LÍMITE VISUAL Y BOTONES DE CONTEXTO
    # --------------------------------------------------------

    # Telegram limita los mensajes a 4096 caracteres.
    # Mostramos hasta 10 eventos y, además, reducimos la lista
    # si el texto se acerca al límite.
    selected_events = []
    current_length = len(str(title)) + 100

    for event in filtered_events:
        if len(selected_events) >= 10:
            break

        formatted = format_calendar_event(event)
        projected = current_length + len(formatted) + 2

        if projected > 3300 and selected_events:
            break

        selected_events.append((event, formatted))
        current_length = projected

    if not selected_events:
        text = (
            f"{title}\n\n"
            "📭 <b>No hay eventos disponibles "
            "para los filtros seleccionados.</b>\n\n"
            "Puedes actualizar o consultar otra fecha/divisa."
        )
        keyboard = []
    else:
        event_texts = []
        keyboard = []

        for event, formatted in selected_events:
            event_key = cache_calendar_event(event)
            event_texts.append(formatted)

            short_name = str(event_value(event, "name", "title", "event") or "Evento")
            if len(short_name) > 34:
                short_name = short_name[:31] + "..."

            keyboard.append([
                InlineKeyboardButton(
                    f"📚 {short_name}",
                    callback_data=f"calendar_context_{event_key}"
                )
            ])

        extra_count = len(filtered_events) - len(selected_events)
        extra_text = (
            f"\n\nℹ️ Hay {extra_count} eventos adicionales. "
            "Usa filtros de fecha o divisa para consultarlos."
            if extra_count > 0 else ""
        )

        text = (
            f"{title}\n\n"
            + "\n\n".join(event_texts)
            + extra_text
            + "\n\nℹ️ Fuente: FinanceCalendar.com"
        )

    keyboard.extend([
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
    ])

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

    start_date, end_date = week_dates()
    events = await fetch_calendar_events(start_date, end_date)

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

    currencies = set()

    for event in events or []:
        if not isinstance(event, dict):
            continue

        currency = event_currency(event).upper().strip()

        if currency:
            currencies.add(currency)

    currencies = sorted(currencies)
    keyboard = []
    row = []

    for currency in currencies:
        flag = currency_flags.get(currency, "💵")
        row.append(
            InlineKeyboardButton(
                f"{flag} {currency}",
                callback_data=f"currency_{currency}"
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    if currencies:
        text = (
            "💵 <b>EVENTOS POR DIVISA</b>\n\n"
            "Estas son únicamente las divisas que tienen "
            "eventos disponibles durante esta semana.\n\n"
            "👇 Selecciona una divisa:"
        )
    else:
        text = (
            "💵 <b>EVENTOS POR DIVISA</b>\n\n"
            "📭 No hay eventos con una divisa identificada "
            "durante el período consultado."
        )

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Volver",
            callback_data="calendar"
        )
    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
# TÉRMINOS Y CONDICIONES / CONSENTIMIENTO
# ============================================================

TERMS_VERSION = "2026-10-06"

TERMS_TEXT = (
    "📜 <b>TÉRMINOS Y ADVERTENCIAS DE USO — APEXQUANT</b>\n\n"
    "⚠️ <b>Importante:</b> Antes de utilizar ApexQuant, lee y comprende estas "
    "advertencias. ApexQuant ofrece contenido educativo, información de mercado, "
    "herramientas y acceso a servicios de CopyTrading relacionados con OneRoyal. "
    "Nada dentro de ApexQuant constituye asesoramiento financiero personalizado "
    "ni garantiza resultados o rentabilidad.\n\n"
    "📊 <b>Trading y riesgo</b>\n"
    "El trading de Forex, CFDs, índices, materias primas, acciones, criptomonedas "
    "u otros instrumentos financieros puede implicar un alto nivel de riesgo. "
    "El apalancamiento puede ampliar tanto las ganancias como las pérdidas. "
    "Nunca arriesgues fondos que no puedas permitirte perder.\n\n"
    "🤖 <b>CopyTrading ApexQuant</b>\n"
    "El CopyTrading no garantiza beneficios. Los resultados pasados no garantizan "
    "resultados futuros y las operaciones copiadas pueden generar pérdidas. "
    "Cada usuario es responsable de su cuenta, capital y configuración de riesgo. "
    "OneRoyal establece las condiciones de su plataforma y de la oferta de CopyTrading.\n\n"
    "💰 <b>Comisiones de CopyTrading</b>\n"
    "ApexQuant no cobra cuota de entrada ni cuota fija de gestión. La oferta puede "
    "aplicar una comisión de rendimiento sobre las ganancias de acuerdo con las "
    "condiciones vigentes de OneRoyal. Si no se generan ganancias sujetas a esa "
    "comisión, no se genera comisión de rendimiento. Revisa siempre las condiciones "
    "mostradas en OneRoyal antes de suscribirte.\n\n"
    "🏦 <b>OneRoyal</b>\n"
    "La cuenta de trading, ejecución, depósitos, retiros, CopyTrading, condiciones "
    "comerciales y requisitos de verificación corresponden a OneRoyal. ApexQuant no "
    "custodia los fondos del usuario ni controla su cuenta de broker.\n\n"
    "👥 <b>Referidos, IB, Sub-IB y Public Agent</b>\n"
    "Las funciones de IB, Sub-IB y Public Agent dependen de la aprobación, acuerdos "
    "y configuración de OneRoyal. Las comisiones se calculan y distribuyen conforme "
    "a las condiciones aplicables de OneRoyal; las tasas no deben interpretarse como "
    "garantizadas por ApexQuant.\n\n"
    "🎓 <b>Academia ApexQuant</b>\n"
    "Todo el contenido educativo, gráficos, conceptos y ejemplos tienen finalidad "
    "formativa. Aprender una metodología no garantiza que una operación futura tenga "
    "un resultado determinado.\n\n"
    "🌎 <b>Elegibilidad por jurisdicción</b>\n"
    "Los servicios de OneRoyal y CopyTrading no están disponibles en todas las "
    "jurisdicciones. El usuario es responsable de comprobar que puede utilizar "
    "legalmente los servicios desde su país de residencia y de cumplir los requisitos "
    "que correspondan.\n\n"
    "🔒 <b>Responsabilidad del usuario</b>\n"
    "Al utilizar ApexQuant, el usuario acepta que toma sus propias decisiones y "
    "asume la responsabilidad por el uso de la información, herramientas y servicios. "
    "Antes de operar o depositar fondos, debe revisar las condiciones oficiales de "
    "OneRoyal y considerar si el producto es adecuado para su situación.\n\n"
    "Al pulsar <b>✅ Acepto y continuar</b>, confirmas que has leído y comprendido "
    "estas advertencias y aceptas utilizarlas bajo tu propia responsabilidad."
)


def load_consents():
    try:
        if not os.path.exists(CONSENTS_FILE):
            return {}
        with open(CONSENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as error:
        logger.error("Error cargando consentimientos: %s", error)
        return {}


def save_consents(data):
    try:
        directory = os.path.dirname(CONSENTS_FILE)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        temp = CONSENTS_FILE + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp, CONSENTS_FILE)
        return True
    except Exception as error:
        logger.error("Error guardando consentimiento: %s", error)
        return False


def has_accepted_terms(user_id):
    return load_consents().get(str(user_id), {}).get("terms_version") == TERMS_VERSION


def register_terms_acceptance(user_id):
    data = load_consents()
    data[str(user_id)] = {
        "terms_version": TERMS_VERSION,
        "accepted_at": datetime.utcnow().isoformat() + "Z"
    }
    return save_consents(data)


def terms_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Leer términos completos", callback_data="terms")],
        [InlineKeyboardButton("✅ Acepto y continuar", callback_data="accept_terms")],
        [InlineKeyboardButton("❌ No acepto", callback_data="reject_terms")]
    ])


def welcome_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Términos y condiciones", callback_data="terms")],
        [InlineKeyboardButton("✅ Acepto y continuar", callback_data="accept_terms")],
        [InlineKeyboardButton("❌ No acepto", callback_data="reject_terms")]
    ])


async def show_terms(query):
    await query.edit_message_text(TERMS_TEXT, parse_mode="HTML", reply_markup=terms_keyboard())


async def show_reject_terms(query):
    text = (
        "❌ <b>ACCESO NO CONFIRMADO</b>\n\n"
        "Para acceder al menú de ApexQuant debes leer y aceptar las advertencias "
        "y condiciones de uso.\n\n"
        "Si decides no aceptarlas, puedes cerrar esta conversación y no utilizar "
        "los servicios de ApexQuant."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Volver a los términos", callback_data="terms")]
    ]))


async def show_main(query):
    membership = await is_community_member(query.get_bot(), query.from_user.id)
    if membership is not True:
        await show_community_gate(query)
        return
    text = (
        "🔥 <b>APEXQUANT</b>\n\n"
        "Bienvenido al ecosistema ApexQuant.\n\n"
        "📊 Mercados · consulta eventos y calendario económico.\n"
        "📋 CopyTrading · sigue la estrategia ApexQuant mediante OneRoyal.\n"
        "👥 Referidos · conoce el sistema IB, Sub-IB y Public Agent.\n"
        "🎓 Academia · formación de trading desde fundamentos hasta aplicación avanzada.\n"
        "🌐 Comunidad · canal y redes oficiales de ApexQuant.\n"
        "🤖 Asistente · información inteligente sobre el ecosistema y los mercados.\n"
        "🟢 OneRoyal · acceso al broker y registro mediante el enlace de ApexQuant.\n\n"
        "⚠️ Opera siempre bajo tu propia responsabilidad."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu(query.from_user.id))


# ============================================================
# REFERIDOS — IB / SUB-IB / PUBLIC AGENT
# ============================================================

async def show_referrals(query):
    text = (
        "👥 <b>REFERIDOS — ECOSISTEMA ONEROYAL</b>\n\n"
        "ApexQuant trabaja la estructura de referidos mediante OneRoyal. "
        "Las comisiones/rebates, atribución y condiciones dependen del acuerdo "
        "y de la configuración aprobada por OneRoyal.\n\n"
        "🏦 <b>1. Registro con OneRoyal</b>\n"
        "Si quieres registrarte como cliente de OneRoyal mediante ApexQuant, utiliza "
        "el enlace de registro de ApexQuant para que la relación quede atribuida "
        "correctamente.\n\n"
        "📈 <b>2. Seguir a ApexQuant (CopyTrading)</b>\n"
        "Con tu cuenta de OneRoyal ya registrada, usa el enlace de proveedor de "
        "CopyTrading para conectarte y seguir la estrategia de ApexQuant.\n\n"
        "🔗 <b>3. ¿Quieres tu propio enlace de afiliado (Sub-IB / Public Agent)?</b>\n"
        "No necesitas buscar ni crear el enlace por tu cuenta. OneRoyal confirmó a "
        "ApexQuant que puede crear los enlaces para sus afiliados, con los "
        "porcentajes y parámetros que ApexQuant defina para cada uno.\n\n"
        "🔄 <b>Cómo funciona la red de afiliados:</b>\n"
        "• ApexQuant te crea tu enlace personal con tus porcentajes y parámetros.\n"
        "• Tú invitas a personas con ese enlace.\n"
        "• Ganas las comisiones que ApexQuant te haya configurado, dentro de las "
        "condiciones de OneRoyal.\n"
        "• Una vez configurado, el sistema distribuye las comisiones de forma "
        "automática.\n\n"
        "📩 <b>4. Solicítalo al manager de ApexQuant</b>\n"
        "Pulsa <b>Contactar al manager de ApexQuant</b> y pide tu enlace. "
        "No te enviaremos un enlace inventado: el enlace real se crea y se "
        "entrega desde la gestión de ApexQuant.\n\n"
        "💵 <b>5. Comisiones</b>\n"
        "Las comisiones que recibe cada afiliado las determina ApexQuant al crear "
        "su enlace, según lo permitido por OneRoyal. No se debe asumir una tasa "
        "concreta sin confirmar el acuerdo aplicable.\n\n"
        "ℹ️ <b>Sub-IB y Public Agent:</b> Sub-IB pertenece a la estructura de IB de "
        "OneRoyal; Public Agent corresponde a ofertas de CopyTrading, donde el "
        "agente puede recibir la parte de las fees que se configure en la oferta "
        "y el seguidor puede tener que introducir el número de cuenta MT del agente "
        "durante la suscripción.\n\n"
        "⚠️ <b>Importante:</b> la disponibilidad de IB, Sub-IB y Public Agent depende "
        "de aprobación, jurisdicción, términos y configuración de OneRoyal."
    )
    keyboard = []
    if ONEROYAL_IB_URL:
        keyboard.append([InlineKeyboardButton("🏦 Registrarme con OneRoyal", url=ONEROYAL_IB_URL)])
    else:
        keyboard.append([
            InlineKeyboardButton(
                "⚠️ Enlace OneRoyal no configurado",
                callback_data="ib_link_missing"
            )
        ])
    if ONEROYAL_COPYTRADING_URL:
        keyboard.append([InlineKeyboardButton("📈 Seguir Apex Quant", url=ONEROYAL_COPYTRADING_URL)])
    else:
        keyboard.append([
            InlineKeyboardButton(
                "⚠️ CopyTrading no configurado",
                callback_data="copy_link_missing"
            )
        ])
    if ADMIN_TELEGRAM_ID:
        keyboard.append([
            InlineKeyboardButton(
                "📩 Contactar al manager de ApexQuant",
                url=f"tg://user?id={ADMIN_TELEGRAM_ID}"
            )
        ])
    keyboard.append([InlineKeyboardButton("📋 Ver CopyTrading ApexQuant", callback_data="copytrading")])
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data="back_main")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

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
    admin_status = "🛠️ Administrador" if is_admin(user_id) else "👤 Usuario"
    text = (
        "⚙️ <b>CONFIGURACIÓN</b>\n\n"
        f"🆔 ID de Telegram: <code>{user_id}</code>\n"
        f"👤 Tipo de cuenta: <b>{admin_status}</b>\n\n"
        "Aquí puedes consultar los términos y advertencias de uso "
        "de ApexQuant y cambiar el idioma de la interfaz.\n\n"
        "⚠️ El trading y el CopyTrading implican riesgo de pérdida de capital."
    )
    keyboard = [
        [InlineKeyboardButton("📜 Términos y condiciones", callback_data="terms")],
        [InlineKeyboardButton("🌐 Cambiar idioma", callback_data="language")],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


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
            "• Apalancamiento y margen.\n"
            "• Contratos, pips, lotaje y tamaño de posición (Parte 2).\n\n"

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
        # Página 2 del Módulo 1 (se abre con el botón "Siguiente").
        "page2": {
            "title": "📘 Módulo 1 — Parte 2: Contratos, Pips y Lotaje",
            "text": (
                "Estos conceptos te permiten medir movimientos y calcular cuánto "
                "se opera. Son la base para entender el riesgo de cada operación.\n\n"

                "📏 Contrato:\n"
                "Es la cantidad estándar de un activo que representa 1 lote. En Forex, "
                "1 lote estándar equivale a 100.000 unidades de la divisa base. En "
                "índices, oro y otras materias primas el tamaño del contrato depende "
                "del broker, por lo que conviene consultar la especificación del "
                "instrumento en tu plataforma.\n\n"

                "📍 Pip:\n"
                "Es la unidad de referencia para medir el movimiento del precio. En la "
                "mayoría de pares equivale a 0,0001 y en pares con JPY a 0,01.\n"
                "Ejemplo: si EUR/USD pasa de 1,1000 a 1,1010, se movió 10 pips.\n\n"

                "💲 Valor del pip:\n"
                "Es cuánto dinero representa un pip según el lotaje. En EUR/USD, con "
                "una cuenta en USD, 1 pip equivale aproximadamente a:\n"
                "• 10 USD con 1.00 lote.\n"
                "• 1 USD con 0.10 lote.\n"
                "• 0,10 USD con 0.01 lote.\n"
                "Varía según el par y la divisa de la cuenta.\n\n"

                "⚖️ Lotaje:\n"
                "Es el volumen de una operación expresado en lotes:\n"
                "• 1.00 = lote estándar (100.000 unidades).\n"
                "• 0.10 = mini lote (10.000 unidades).\n"
                "• 0.01 = micro lote (1.000 unidades).\n"
                "A mayor lotaje, mayor valor por pip: las ganancias y las pérdidas "
                "se amplifican en la misma proporción.\n\n"

                "🧮 Tamaño de posición:\n"
                "Es la cantidad que se opera, calculada a partir del capital, el "
                "porcentaje de riesgo y la distancia al Stop Loss. Fórmula:\n"
                "Lotaje = Riesgo en dinero ÷ (Stop Loss en pips × valor del pip por lote)\n\n"

                "📌 Ejemplo educativo:\n"
                "Cuenta de 1.000 USD, riesgo del 1% (10 USD), Stop Loss de 20 pips "
                "en EUR/USD (10 USD por pip con 1 lote).\n"
                "Lotaje = 10 ÷ (20 × 10) = 0.05 lotes.\n\n"

                "⚠️ El tamaño de posición no es lo mismo que el apalancamiento ni que "
                "el margen: define cuánto puedes perder si el Stop Loss se activa. "
                "Es un ejemplo con fines educativos, no una recomendación."
            ),
        },
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
    # "m1_p2" = página 2 del módulo "m1".
    page = 1
    base_id = module_id
    if module_id.endswith("_p2"):
        base_id = module_id[:-3]
        page = 2

    module = ACADEMY_MODULES.get(base_id)
    if not module or (page == 2 and not module.get("page2")):
        await show_academy(query)
        return

    keyboard = []

    if page == 2:
        content = module["page2"]
        keyboard.append([InlineKeyboardButton("⬅️ Parte 1", callback_data=f"academy_{base_id}")])
        disclaimer = (
            "⚠️ <b>Contenido educativo:</b> los ejemplos son ilustrativos y no "
            "constituyen una recomendación de operación."
        )
    else:
        content = module
        if module.get("visual"):
            keyboard.append([InlineKeyboardButton("🖼️ Ver material visual", callback_data=f"academy_visual_{module['visual']}")])
        if module.get("page2"):
            keyboard.append([InlineKeyboardButton("➡️ Siguiente: Contratos, pips y lotaje", callback_data=f"academy_{base_id}_p2")])
        disclaimer = "⚠️ <b>Contenido educativo:</b> estudiar un concepto no garantiza que una operación futura tenga un resultado determinado."

    keyboard.extend([
        [InlineKeyboardButton("🎓 Academia", callback_data="academy")],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back_main")],
    ])
    text = (
        f"{content['title']}\n\n"
        f"{content['text']}\n\n"
        f"{disclaimer}"
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
# COMANDO /START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return

    user_id = user.id

    # 1. Primero se comprueba la aceptación de los términos.
    if not has_accepted_terms(user_id):
        await update.message.reply_text(
            TERMS_TEXT,
            parse_mode="HTML",
            reply_markup=terms_keyboard()
        )
        return

    # 2. Con los términos aceptados, se comprueba el acceso a la Comunidad.
    membership = await is_community_member(context.bot, user_id)

    if membership is not True:
        await update.message.reply_text(
            "🌐 <b>COMUNIDAD APEXQUANT</b>\n\n"
            "Tus términos ya están aceptados. Antes de acceder al menú principal "
            "debes formar parte de la Comunidad oficial de ApexQuant.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Unirme al canal", url=COMMUNITY_INVITE_URL)],
                [InlineKeyboardButton("✅ Verificar acceso", callback_data="community_verify")]
            ])
        )
        return

    # 3. Términos aceptados + Comunidad verificada = menú principal.
    text = (
        "🔥 <b>Bienvenido a ApexQuant</b>\n\n"
        "Centro de información, formación y herramientas relacionadas con los mercados financieros.\n\n"
        "📊 <b>Mercados</b> — calendario económico y eventos relevantes.\n"
        "📋 <b>CopyTrading</b> — acceso a la oferta ApexQuant en OneRoyal.\n"
        "👥 <b>Referidos</b> — guía de IB, Sub-IB y Public Agent.\n"
        "🎓 <b>Academia</b> — formación progresiva de trading.\n"
        "🌐 <b>Comunidad</b> — canal y redes oficiales de ApexQuant.\n"
        "🟢 <b>OneRoyal</b> — broker y registro mediante ApexQuant.\n\n"
        "⚠️ <b>Aviso de riesgo:</b> ningún contenido de ApexQuant garantiza resultados financieros."
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(user_id)
    )



# ============================================================
# ADMINISTRACIÓN — COMUNIDAD
# ============================================================

def admin_menu_keyboard():
    count = community_post_count()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 Publicar texto ({count}/{COMMUNITY_DAILY_TARGET})", callback_data="admin_community_text")],
        [InlineKeyboardButton("🖼️ Publicar imagen", callback_data="admin_community_photo")],
        [InlineKeyboardButton("🎓 Publicar Academia", callback_data="admin_community_academy")],
        [InlineKeyboardButton("📊 Estado de publicaciones", callback_data="admin_community_stats")],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]
    ])


async def show_admin_menu(query):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return
    channel_status = "🟢 Canal conectado" if get_community_channel_id() else "🟡 Canal pendiente de detección"
    text = ("🛠️ <b>ADMINISTRACIÓN — COMUNIDAD</b>\n\n" f"{channel_status}\n" f"📅 Publicaciones manuales hoy: <b>{community_post_count()}/{COMMUNITY_DAILY_TARGET}</b>\n\n" "📢 Desde aquí puedes mantener activa la Comunidad con publicaciones manuales.\n\n" "🚨 Las alertas automáticas de alto impacto funcionan por separado y no consumen el objetivo de 3 publicaciones manuales.")
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_menu_keyboard())


async def admin_send_text_prompt(query, context):
    if not is_admin(query.from_user.id): return
    context.user_data["admin_action"] = "community_text"
    await query.edit_message_text("📝 <b>NUEVA PUBLICACIÓN</b>\n\nEscribe ahora el texto que quieres publicar en el canal.\n\nPuedes utilizar emojis y HTML básico.\n\n❌ /cancelar para cancelar.", parse_mode="HTML")


async def admin_send_photo_prompt(query, context):
    if not is_admin(query.from_user.id): return
    context.user_data["admin_action"] = "community_photo"
    await query.edit_message_text("🖼️ <b>PUBLICAR IMAGEN</b>\n\nEnvíame ahora la imagen desde este chat. Puedes incluir la descripción como caption.\n\n❌ /cancelar para cancelar.", parse_mode="HTML")


async def admin_academy_menu(query):
    if not is_admin(query.from_user.id): return
    buttons=[]
    for module_id,module in ACADEMY_MODULES.items():
        buttons.append([InlineKeyboardButton(module["title"], callback_data=f"admin_academy_{module_id}")])
    buttons.append([InlineKeyboardButton("🔙 Administración", callback_data="admin_menu")])
    await query.edit_message_text("🎓 <b>PUBLICAR ACADEMIA</b>\n\nSelecciona el módulo que quieres publicar.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def publish_academy_module(context, module_id):
    channel_id=get_community_channel_id(); module=ACADEMY_MODULES.get(module_id)
    if not channel_id or not module: return False
    # Contenido a publicar: página principal y, si existe, la página 2.
    pages=[module]
    if module.get("page2"): pages.append(module["page2"])
    for page_index,page in enumerate(pages):
        text=f"🎓 <b>{page['title']}</b>\n\n{page['text']}"
        if page_index==len(pages)-1:
            text+="\n\n⚠️ <b>Contenido educativo:</b> estudiar una metodología no garantiza resultados futuros."
        chunks=[]
        while len(text)>3900:
            cut=text.rfind("\n",0,3900)
            if cut<1000: cut=3900
            chunks.append(text[:cut]); text=text[cut:].lstrip()
        if text: chunks.append(text)
        for chunk in chunks:
            await context.bot.send_message(chat_id=channel_id,text=chunk,parse_mode="HTML")
    register_community_post(); return True


async def admin_publish_academy(query, context, module_id):
    if not is_admin(query.from_user.id): return
    ok=await publish_academy_module(context,module_id)
    if ok:
        await query.edit_message_text("✅ <b>Contenido de Academia publicado.</b>\n\n" f"📅 Publicaciones manuales hoy: {community_post_count()}/{COMMUNITY_DAILY_TARGET}",parse_mode="HTML",reply_markup=admin_menu_keyboard())
    else:
        await query.edit_message_text("⚠️ No se pudo publicar. Verifica que el canal esté detectado y que el bot sea administrador.",parse_mode="HTML",reply_markup=admin_menu_keyboard())


async def admin_stats(query):
    if not is_admin(query.from_user.id): return
    await query.edit_message_text("📊 <b>ESTADO DE COMUNIDAD</b>\n\n" f"📅 Publicaciones manuales hoy: <b>{community_post_count()}/{COMMUNITY_DAILY_TARGET}</b>\n" f"📢 Canal: <code>{get_community_channel_id() or 'Pendiente de detección'}</code>\n\n" "🚨 Las alertas automáticas de alto impacto son independientes.",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Administración",callback_data="admin_menu")]]))


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not is_admin(update.effective_user.id): return
    context.user_data.pop("admin_action",None)
    await update.message.reply_text("❌ Publicación cancelada.",reply_markup=admin_menu_keyboard())


async def admin_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post or not update.message or not update.effective_user or not is_admin(update.effective_user.id): return
    if context.user_data.get("admin_action") != "community_text": return
    channel_id=get_community_channel_id()
    if not channel_id:
        context.user_data.pop("admin_action",None)
        await update.message.reply_text("⚠️ El canal todavía no ha sido detectado. Publica un mensaje en el canal oficial una vez y vuelve a intentarlo.",reply_markup=admin_menu_keyboard()); return
    await context.bot.send_message(chat_id=channel_id,text=update.message.text,parse_mode="HTML")
    count=register_community_post(); context.user_data.pop("admin_action",None)
    await update.message.reply_text(f"✅ Publicación enviada.\n\n📅 Publicaciones manuales hoy: {count}/{COMMUNITY_DAILY_TARGET}",reply_markup=admin_menu_keyboard())


async def admin_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post or not update.message or not update.effective_user or not is_admin(update.effective_user.id): return
    if context.user_data.get("admin_action") != "community_photo": return
    channel_id=get_community_channel_id()
    if not channel_id:
        context.user_data.pop("admin_action",None)
        await update.message.reply_text("⚠️ El canal todavía no ha sido detectado. Publica un mensaje en el canal oficial una vez y vuelve a intentarlo.",reply_markup=admin_menu_keyboard()); return
    await context.bot.send_photo(chat_id=channel_id,photo=update.message.photo[-1].file_id,caption=update.message.caption or "",parse_mode="HTML")
    count=register_community_post(); context.user_data.pop("admin_action",None)
    await update.message.reply_text(f"✅ Imagen publicada.\n\n📅 Publicaciones manuales hoy: {count}/{COMMUNITY_DAILY_TARGET}",reply_markup=admin_menu_keyboard())


async def community_high_impact_monitor(application):
    while True:
        try:
            channel_id=get_community_channel_id()
            if channel_id:
                today=date.today(); events=await fetch_calendar_events(today,today)
                seen=_load_json_file(COMMUNITY_EVENTS_FILE,{})
                now=datetime.now(timezone.utc); changed=False
                for event in events or []:
                    if str(event_value(event,"impact","importance")).lower()!="high": continue
                    name=str(event_value(event,"name","title","event") or "Evento económico")
                    currency=event_currency(event).upper() or "N/D"
                    raw_dt=event_value(event,"time_utc","datetime","date")
                    if not raw_dt: continue
                    try:
                        dt=datetime.fromisoformat(str(raw_dt).strip().replace("Z","+00:00"))
                    except ValueError: continue
                    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    dt=dt.astimezone(timezone.utc)
                    minutes=(dt-now).total_seconds()/60
                    if minutes < -5 or minutes > 30: continue
                    key=str(event_value(event,"id","event_id") or f"{name}|{currency}|{raw_dt}")
                    if key in seen: continue
                    message=("🚨 <b>EVENTO ECONÓMICO DE ALTO IMPACTO</b>\n\n" f"🔴 <b>{escape(currency)}</b>\n" f"📰 {escape(name)}\n" f"🕒 {dt.strftime('%Y-%m-%d %H:%M UTC')}\n\n" "⚠️ Este evento puede generar volatilidad elevada y movimientos bruscos.\n\n" "🛡️ Gestiona tu riesgo y considera el contexto económico.\n\n" "ApexQuant — información de mercado, no una señal de entrada.")
                    await application.bot.send_message(chat_id=channel_id,text=message,parse_mode="HTML")
                    seen[key]=datetime.utcnow().isoformat()+"Z"; changed=True
                if changed:
                    for old_key in list(seen)[:-500]: seen.pop(old_key,None)
                    _save_json_file(COMMUNITY_EVENTS_FILE,seen)
        except asyncio.CancelledError: raise
        except Exception as error: logger.error("Error en monitor de alto impacto: %s",error,exc_info=True)
        await asyncio.sleep(HIGH_IMPACT_CHECK_SECONDS)



# ============================================================
# ASISTENTE APEXQUANT — FASE 2
# ============================================================

APEXQUANT_ASSISTANT_INSTRUCTIONS = """
Eres el Asistente ApexQuant, el asistente oficial del ecosistema ApexQuant.
Responde principalmente en español, salvo que el usuario escriba claramente
en otro idioma.

MISIÓN
- Explicar el ecosistema ApexQuant: Mercados, calendario económico, Academia,
  CopyTrading, OneRoyal, Referidos, IB, Sub-IB, Public Agent y Comunidad.
- Ayudar con trading, Forex, índices, materias primas, criptomonedas,
  macroeconomía, análisis técnico, fundamental e institucional.
- Explicar conceptos de la Academia con claridad y ejemplos educativos.
- Para información actual, usar búsqueda web cuando esté habilitada.
- No inventar enlaces, porcentajes, condiciones de OneRoyal, disponibilidad
  regional ni datos de mercado.

APEXQUANT
ApexQuant es un ecosistema de información, educación y herramientas relacionadas
con mercados financieros. La Academia cubre desde fundamentos hasta estructura,
liquidez, BOS, CHOCH, FVG, Order Blocks, Premium/Discount, análisis
multitemporal y flujo de análisis.
El calendario económico utiliza FinanceCalendar y puede complementarse con web.
ApexQuant integra OneRoyal para registro y CopyTrading mediante sus enlaces.
El CopyTrading no garantiza beneficios y sus condiciones las determina OneRoyal.
ApexQuant no custodia fondos ni controla cuentas de broker.

ONEROYAL — REFERIDOS, IB, SUB-IB Y PUBLIC AGENT
La información oficial consultada indica que los IB pueden usar enlaces
personalizados, seguir clientes y comisiones mediante herramientas del portal,
y que existe una estructura Master IB/Sub-IB sujeta a aprobación y condiciones.
IMPORTANTE PARA APEXQUANT: el manager de OneRoyal de ApexQuant confirmó que
ApexQuant puede crear los enlaces para sus Sub-IB y puede crear todos los enlaces
que necesite. Por eso, si un usuario quiere un enlace Sub-IB o un enlace de
referido generado por ApexQuant, NO le digas que debe solicitarlo directamente
a OneRoyal: indícale que debe solicitarlo al equipo/administrador de ApexQuant
mediante el botón «Contactar al manager de ApexQuant» disponible en Referidos. No inventes ni fabriques
URLs de Sub-IB. El administrador de ApexQuant es quien gestiona la creación y
entrega del enlace correspondiente.

DIFERENCIA IMPORTANTE: Sub-IB pertenece a la estructura de partners/IB de
OneRoyal y recibe su propio enlace de referidos cuando ApexQuant lo crea para él.
Public Agent corresponde a ofertas de CopyTrading; cuando está habilitado, el
seguidor puede necesitar introducir el número de cuenta MT del agente y las
comisiones dependen de la configuración de la oferta.
Nunca prometas una tasa de comisión concreta si no está confirmada para esa
campaña o acuerdo.
Cuando Public Agent está habilitado para una oferta, OneRoyal indica que el
agente puede recibir una parte de las fees de la oferta, incluyendo performance,
management o registration fees, y que el seguidor debe introducir el número de
cuenta MT del agente durante la suscripción. Depende de la oferta y configuración.

TRADING Y PROYECCIONES
Si preguntan si un activo subirá/bajará, por una entrada, compra/venta, señal o
proyección:
- Nunca presentes una predicción como certeza ni prometas resultados.
- Puedes ofrecer escenarios alcista, bajista y neutral, con condiciones de
  confirmación e invalidación.
- Puedes analizar estructura, liquidez, volatilidad, catalizadores y riesgo si
  hay datos actuales suficientes.
- Valida siempre precio y contexto actual antes de una decisión.
- No sustituyas asesoramiento financiero personalizado.

ACTUALIDAD
Para noticias, eventos, datos macro, condiciones de mercado, OneRoyal, precios
o cualquier dato cambiante, usa web si está habilitada. Si no puedes verificar
algo, dilo claramente.

ESTILO
Sé útil, directo y profesional. Usa secciones cortas y emojis con moderación.
Incluye una advertencia clara cuando la pregunta implique una decisión financiera.
"""

def assistant_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧹 Nueva conversación", callback_data="assistant_reset")],
        [InlineKeyboardButton("👥 Referidos / enlaces OneRoyal", callback_data="referrals")],
        [InlineKeyboardButton("📅 Calendario económico", callback_data="calendar")],
        [InlineKeyboardButton("🎓 Academia", callback_data="academy")],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]
    ])

def assistant_relevant_calendar(question):
    q = str(question or "").lower()
    return any(k in q for k in (
        "calendario", "evento", "eventos", "cpi", "ppi", "nfp", "fomc",
        "fed", "beige book", "jobless", "desempleo", "inflación", "gdp",
        "pib", "ventas minoristas", "tipo de interés", "interest rate",
        "macro", "mañana", "hoy", "esta semana"
    ))

async def assistant_calendar_context(question):
    if not assistant_relevant_calendar(question):
        return ""
    try:
        events = await fetch_calendar_events(today_date(), tomorrow_date())
        rows = []
        for event in events or []:
            if not isinstance(event, dict):
                continue
            name = str(event_value(event, "name", "title", "event") or "")
            if not name:
                continue
            currency = event_currency(event) or "N/D"
            impact = str(event_value(event, "impact", "importance") or "N/D")
            dt = str(event_value(event, "time_utc", "datetime", "date") or "")
            rows.append(f"- {dt} | {impact.upper()} | {currency} | {name}")
            if len(rows) >= 12:
                break
        return "\n\nCALENDARIO APEXQUANT:\n" + "\n".join(rows) if rows else ""
    except Exception as error:
        logger.warning("No se pudo adjuntar calendario al asistente: %s", error)
        return ""

def assistant_extract_output(data):
    pieces = []
    try:
        candidates = data.get("candidates", []) if isinstance(data, dict) else []
        for candidate in candidates:
            content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
            for part in content.get("parts", []) or []:
                if isinstance(part, dict) and part.get("text") and not part.get("thought"):
                    pieces.append(str(part["text"]))
    except Exception:
        pass
    return "\n".join(pieces).strip()

def assistant_gemini_contents(history, question):
    contents = []

    for item in (history or [])[-ASSISTANT_MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue

        role_value = item.get("role")
        content = str(item.get("content", "")).strip()

        if not content:
            continue

        if role_value in {"assistant", "model"}:
            role = "model"
        else:
            role = "user"

        contents.append({
            "role": role,
            "parts": [
                {
                    "text": content
                }
            ]
        })

    contents.append({
        "role": "user",
        "parts": [
            {
                "text": str(question)
            }
        ]
    })

    return contents

async def assistant_web_search_context(question):
    """Obtiene contexto web reciente mediante Gemini Search, separado de Gemma."""
    if not GEMINI_WEB_SEARCH or not GEMINI_SEARCH_API_KEY:
        return ""

    payload = {
        "systemInstruction": {
            "parts": [{
                "text": (
                    "Eres el motor de investigación web de ApexQuant. "
                    "Busca información reciente y relevante para responder la pregunta. "
                    "No intentes dar una respuesta final extensa. Devuelve únicamente hechos, "
                    "fechas, cifras y contexto verificable que otro modelo pueda utilizar. "
                    "Si la información no es verificable o no aparece en fuentes recientes, indícalo."
                )
            }]
        },
        "contents": [{"role": "user", "parts": [{"text": str(question)}]}],
        "generationConfig": {
            "maxOutputTokens": 1200,
            "temperature": 0.2
        },
        "tools": [{"google_search": {}}]
    }

    def request_search():
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_SEARCH_MODEL}:generateContent"
        )
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "x-goog-api-key": GEMINI_SEARCH_API_KEY,
                "Content-Type": "application/json"
            }
        )
        try:
            with urlopen(request, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            logger.warning(
                "Gemini web search HTTP %s para modelo %s: %s",
                error.code, GEMINI_SEARCH_MODEL, error_body[:1000]
            )
            return {}

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, request_search)
        result = assistant_extract_output(data)
        return result[:ASSISTANT_WEB_CONTEXT_MAX].strip()
    except Exception as error:
        logger.warning("Error en búsqueda web del asistente: %s", error)
        return ""


async def assistant_notify_admin(notify_bot, text):
    """Envía un aviso de diagnóstico solo al administrador (sin exponer API keys)."""
    if not notify_bot or not ADMIN_TELEGRAM_ID:
        return
    try:
        await notify_bot.send_message(chat_id=int(ADMIN_TELEGRAM_ID), text=text[:3500])
    except Exception as notify_error:
        logger.warning("No se pudo avisar al admin: %s", notify_error)


async def call_apexquant_assistant(question, history, calendar_context="", web_context="", notify_bot=None):
    if not GEMMA_API_KEY:
        return (
            "⚠️ <b>Asistente ApexQuant</b>\n\n"
            "El asistente IA todavía no está conectado.\n\n"
            "Configura <code>GEMMA_API_KEY</code> en Deployka.\n\n"
            "También puedes mantener <code>GEMINI_API_KEY</code> como respaldo para la búsqueda web."
        )

    instructions = APEXQUANT_ASSISTANT_INSTRUCTIONS
    if calendar_context:
        instructions += "\n\n" + calendar_context
    if web_context:
        instructions += (
            "\n\nCONTEXTO WEB RECIENTE — úsalo como información de apoyo y "
            "no inventes datos que no aparezcan aquí:\n" + web_context
        )

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": instructions
                }
            ]
        },
        "contents": assistant_gemini_contents(history, question),
        "generationConfig": {
            "maxOutputTokens": ASSISTANT_MAX_OUTPUT + ASSISTANT_THINKING_HEADROOM,
            "temperature": 1.0,
            "topP": 0.95,
            "topK": 64
        }
    }

    def request_gemma():
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = GEMMA_API_URL.format(model=GEMMA_MODEL)
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "x-goog-api-key": GEMMA_API_KEY,
                "Content-Type": "application/json"
            }
        )
        try:
            with urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            logger.error(
                "Gemma HTTP %s para modelo %s: %s",
                error.code, GEMMA_MODEL, error_body[:1500]
            )
            raise RuntimeError(
                f"Gemma HTTP {error.code} para modelo {GEMMA_MODEL}: {error_body[:500]}"
            ) from error

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, request_gemma)
        answer = assistant_extract_output(data)
        if not answer:
            try:
                cand = (data.get("candidates") or [{}])[0] if isinstance(data, dict) else {}
                logger.warning(
                    "Gemma devolvió respuesta vacía. finishReason=%s, promptFeedback=%s, usage=%s",
                    cand.get("finishReason"),
                    data.get("promptFeedback") if isinstance(data, dict) else None,
                    data.get("usageMetadata") if isinstance(data, dict) else None
                )
            except Exception:
                logger.warning("Gemma devolvió respuesta vacía (no se pudo leer el detalle).")
            try:
                cand0 = (data.get("candidates") or [{}])[0] if isinstance(data, dict) else {}
                await assistant_notify_admin(
                    notify_bot,
                    "🛠 DEBUG Asistente: respuesta vacía de Gemma\n"
                    f"finishReason={cand0.get('finishReason')}\n"
                    f"promptFeedback={data.get('promptFeedback') if isinstance(data, dict) else None}\n"
                    f"usage={data.get('usageMetadata') if isinstance(data, dict) else None}"
                )
            except Exception:
                pass
        return answer or "⚠️ No pude generar una respuesta en este momento."
    except Exception as error:
        logger.error("Error en Asistente ApexQuant/Gemma [%s]: %s", type(error).__name__, error, exc_info=True)
        error_text = str(error)
        await assistant_notify_admin(
            notify_bot,
            f"🛠 DEBUG Asistente: {type(error).__name__}\n{error_text[:900]}"
        )
        if "HTTP 404" in error_text:
            return (
                "⚠️ <b>Gemma 4 no está disponible para esta API Key/proyecto.</b>\n\n"
                f"Modelo configurado: <code>{GEMMA_MODEL}</code>\n\n"
                "La clave llegó al servidor, pero Google no habilitó ese modelo para el proyecto. "
                "Revisaremos la disponibilidad antes de cambiar la clave."
            )
        if "HTTP 400" in error_text:
            return (
                "⚠️ <b>Gemma 4 rechazó la solicitud.</b>\n\n"
                "La API recibió la clave, pero rechazó el formato o algún parámetro de la petición.\n\n"
                "El administrador puede revisar los detalles en los Logs de Deployka."
            )
        if "HTTP 401" in error_text or "HTTP 403" in error_text:
            return (
                "⚠️ <b>Google rechazó la API Key.</b>\n\n"
                "Revisa que la clave esté activa en Deployka y pertenezca al proyecto correcto."
            )
        if "HTTP 429" in error_text:
            return (
                "⚠️ <b>El asistente está recibiendo demasiadas consultas.</b>\n\n"
                "Espera un momento e inténtalo nuevamente."
            )
        if any(code in error_text for code in ("HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")):
            return (
                "⚠️ <b>El servicio de IA no está disponible temporalmente.</b>\n\n"
                "Inténtalo nuevamente en unos minutos."
            )
        if "timed out" in error_text.lower() or "timeout" in error_text.lower():
            return (
                "⚠️ <b>El asistente tardó demasiado en responder.</b>\n\n"
                "Inténtalo nuevamente en unos segundos."
            )
        return (
            "⚠️ <b>No pude consultar el asistente.</b>\n\n"
            "Gemma 4 devolvió un error. El detalle quedó registrado en Deployka sin exponer la API Key."
        )

async def show_assistant(query, context):
    context.user_data["apex_assistant_active"] = True
    text = (
        "🤖 <b>ASISTENTE APEXQUANT</b>\n\n"
        "Soy el asistente inteligente del ecosistema ApexQuant.\n\n"
        "📊 Mercados y macroeconomía\n"
        "📅 Eventos económicos\n"
        "📈 Trading y análisis técnico/fundamental/institucional\n"
        "🎓 Academia ApexQuant\n"
        "📋 CopyTrading\n"
        "🟢 OneRoyal\n"
        "👥 IB, Sub-IB, Public Agent y referidos\n"
        "🌐 Información reciente de la web\n\n"
        "💬 <b>Escríbeme tu pregunta.</b>\n\n"
        "⚠️ En proyecciones de activos mostraré escenarios y riesgos, no certezas."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=assistant_keyboard())

async def assistant_reset(query, context):
    context.user_data["assistant_history"] = []
    context.user_data["apex_assistant_active"] = True
    text = "🧹 <b>NUEVA CONVERSACIÓN</b>\n\nListo. ¿Qué quieres consultar?"
    current_text = query.message.text if query.message else ""

    # Si ya estamos en este mismo estado, no volvemos a editar el mensaje.
    # Aun así confirmamos visualmente la acción mediante el aviso de Telegram.
    if current_text == "🧹 NUEVA CONVERSACIÓN\n\nListo. ¿Qué quieres consultar?":
        await query.answer("🧹 Conversación reiniciada. Escribe tu pregunta.", show_alert=False)
        return

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=assistant_keyboard()
    )
    await query.answer("🧹 Conversación nueva. Escribe tu pregunta.", show_alert=False)

async def assistant_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post or not update.message or not update.effective_user:
        return
    if context.user_data.get("admin_action") or not context.user_data.get("apex_assistant_active"):
        return

    question = (update.message.text or "").strip()
    if not question:
        return

    history = context.user_data.get("assistant_history", [])
    if not isinstance(history, list):
        history = []

    calendar_context = await assistant_calendar_context(question)
    web_context = ""
    if assistant_relevant_calendar(question) or any(k in question.lower() for k in (
        "actual", "actualmente", "último", "última", "últimos", "últimas",
        "hoy", "ahora", "reciente", "recientes", "noticia", "noticias",
        "precio", "cotización", "mercado", "mercados", "qué pasó",
        "que paso", "últimas noticias", "latest", "today", "current"
    )):
        web_context = await assistant_web_search_context(question)

    await update.message.chat.send_action("typing")
    answer = await call_apexquant_assistant(
        question, history, calendar_context, web_context,
        notify_bot=context.bot
    )

    history.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer}
    ])
    context.user_data["assistant_history"] = history[-ASSISTANT_MAX_HISTORY:]

    try:
        await update.message.reply_text(
            answer[:3900],
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=assistant_keyboard()
        )
    except Exception as send_error:
        # Si el modelo devuelve HTML inválido (por ejemplo "<" o "&" sueltos),
        # se reenvía como texto plano para que el usuario siempre reciba respuesta.
        logger.warning("Respuesta del asistente con HTML inválido, se reenvía en texto plano: %s", send_error)
        await update.message.reply_text(
            answer[:3900],
            disable_web_page_preview=True,
            reply_markup=assistant_keyboard()
        )

# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    try:
        if data == "terms":
            await show_terms(query)
            return

        if data == "accept_terms":
            if register_terms_acceptance(user_id):
                await show_community_gate(query)
            else:
                await query.edit_message_text(
                    "⚠️ No se pudo guardar tu aceptación. Inténtalo nuevamente.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 Términos", callback_data="terms")]])
                )
            return

        if data == "reject_terms":
            await show_reject_terms(query)
            return

        if not has_accepted_terms(user_id):
            await show_terms(query)
            return

        if data == "community_gate":
            await show_community_gate(query)
            return
        if data == "community_verify":
            await verify_community_access(query)
            return
        if data == "community":
            await show_community(query)
            return
        if data == "assistant":
            await show_assistant(query, context)
            return
        if data == "assistant_reset":
            await assistant_reset(query, context)
            return
        if data == "back_main":
            await show_main(query)
            return
        if data == "broker_oneroyal":
            await show_broker_oneroyal(query)
            return
        if data == "markets":
            await show_markets(query)
            return
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
        if data.startswith("calendar_context_"):
            event_key = data.replace("calendar_context_", "", 1)
            await show_calendar_context(query, event_key)
            return
        if data.startswith("currency_"):
            await show_currency_events(query, data.replace("currency_", "", 1))
            return
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
        if data == "referrals":
            await show_referrals(query)
            return
        if data == "language":
            await show_language(query)
            return
        if data == "language_es":
            await set_language(query, "es")
            return
        if data == "language_en":
            await set_language(query, "en")
            return
        if data == "settings":
            await show_settings(query)
            return
        if data == "admin_menu":
            await show_admin_menu(query)
            return
        if data == "admin_community_text":
            await admin_send_text_prompt(query, context)
            return
        if data == "admin_community_photo":
            await admin_send_photo_prompt(query, context)
            return
        if data == "admin_community_academy":
            await admin_academy_menu(query)
            return
        if data.startswith("admin_academy_"):
            await admin_publish_academy(query, context, data.replace("admin_academy_", "", 1))
            return
        if data == "admin_community_stats":
            await admin_stats(query)
            return
        if data == "academy":
            await show_academy(query)
            return
        if data.startswith("academy_m"):
            await show_academy_module(query, data.replace("academy_", "", 1))
            return
        if data.startswith("academy_visual_"):
            await show_academy_visual(query, data.replace("academy_visual_", "", 1))
            return

        await query.edit_message_text(
            "⚠️ <b>Opción no disponible.</b>\n\nRegresa al menú principal.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú principal", callback_data="back_main")]])
        )
    except Exception as error:
        logger.error("Error en button_handler: %s", error, exc_info=True)
        try:
            await query.edit_message_text(
                "⚠️ <b>Se produjo un error.</b>\n\nIntenta nuevamente desde el menú principal.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú principal", callback_data="back_main")]])
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

async def post_init(application):
    application.create_task(community_high_impact_monitor(application), name="apexquant_high_impact_monitor")
    logger.info("🚨 Monitor de eventos de alto impacto iniciado.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN no está configurado.")

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start), group=0)
    application.add_handler(CommandHandler("cancelar", admin_cancel), group=0)
    application.add_handler(CallbackQueryHandler(button_handler), group=0)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_input), group=0)
    # El manejador de administración acepta cualquier texto en group=0.
    # El asistente va en group=1 para recibir también los mensajes normales
    # cuando no hay una acción administrativa activa.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, assistant_text_input), group=1)
    application.add_handler(MessageHandler(filters.PHOTO, admin_photo_input), group=0)
    application.add_handler(MessageHandler(filters.ALL, capture_channel_post), group=1)
    application.add_error_handler(error_handler)

    logger.info("🔥 Apex Quant Bot iniciado correctamente.")
    application.run_polling(drop_pending_updates=True)


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":
    main()
