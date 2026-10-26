# -*- coding: utf-8 -*-

import os
import re
import logging
import asyncio
import json
import io
import hashlib
import time
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from html import escape
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from datetime import datetime, timedelta, date, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
try:
    from telegram.error import BadRequest, Forbidden, RetryAfter
except ImportError:  # versiones antiguas de python-telegram-bot
    from telegram.error import BadRequest, RetryAfter
    from telegram.error import Unauthorized as Forbidden
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
GEMINI_SEARCH_MODEL = os.getenv("GEMINI_SEARCH_MODEL", "gemini-3.8-flash").strip()
# Si el modelo configurado devuelve 404 (retirado/no disponible), se prueban estos en orden.
GEMINI_MODEL_FALLBACKS = [
    m.strip() for m in os.getenv(
        "GEMINI_MODEL_FALLBACKS",
        "gemini-3.8-flash,gemini-flash-latest,gemini-flash-lite-latest"
    ).split(",") if m.strip()
]
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

# Clave gratuita opcional de FinanceCalendar: sube el límite de 2.000 a 10.000
# consultas por día. Se configura en Deployka como FINANCECALENDAR_API_KEY.
FINANCE_CALENDAR_API_KEY = _clean_key(os.getenv("FINANCECALENDAR_API_KEY"))

# Zona horaria en la que el bot muestra las horas del calendario (formato IANA:
# America/Bogota, America/Mexico_City, Europe/Madrid, etc.). Se configura en
# Deployka como CALENDAR_TZ. Si no existe, se usa UTC.
CALENDAR_TZ_NAME = (os.getenv("CALENDAR_TZ", "UTC") or "UTC").strip()

# Los eventos se guardan 2 minutos en memoria para no gastar el límite diario
# de consultas de FinanceCalendar.
CALENDAR_CACHE_SECONDS = 120
CALENDAR_PAGE_SIZE = 8

# Sólo se piden eventos económicos y de bancos centrales. El feed también trae
# eventos cripto (vesting, votaciones DAO...) sin divisa ni impacto que no
# pertenecen a este calendario.
CALENDAR_CATEGORIES = ("economic-indicators", "central-banks-monetary-policy")

# Las subastas del Tesoro de EE. UU. se publican como impacto "medio" y llenan
# la lista. Se ocultan salvo que CALENDAR_SHOW_AUCTIONS=true.
CALENDAR_SHOW_AUCTIONS = os.getenv(
    "CALENDAR_SHOW_AUCTIONS", "false"
).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_calendar_tz(name):
    if ZoneInfo is None:
        logger.warning("zoneinfo no disponible: las horas del calendario se muestran en UTC.")
        return timezone.utc, "UTC"
    try:
        return ZoneInfo(name), name
    except Exception as error:
        logger.warning(
            "CALENDAR_TZ=%r no es válida o falta el paquete tzdata (%s). "
            "Se usa UTC. Si la zona es correcta, añade 'tzdata' a requirements.txt.",
            name, error
        )
        return timezone.utc, "UTC"


CALENDAR_TZ, CALENDAR_TZ_LABEL = _resolve_calendar_tz(CALENDAR_TZ_NAME)

CALENDAR_CURRENCY_FLAGS = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "JPY": "🇯🇵",
    "CHF": "🇨🇭",
    "CAD": "🇨🇦",
    "AUD": "🇦🇺",
    "NZD": "🇳🇿"
}

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

# ------------------------------------------------------------
# TÉRMINOS Y CONDICIONES DE COPYTRADING (botón dentro del menú)
# ------------------------------------------------------------
# El texto se divide automáticamente en páginas para respetar el límite
# de Telegram (4096 caracteres por mensaje). Se corta siempre por secciones
# o párrafos completos, nunca a mitad de frase.

COPY_TERMS_TITLE = "TÉRMINOS Y CONDICIONES — APEXQUANT COPYTRADING"

COPY_TERMS_SECTIONS = [
    (
        "1. Nuestra filosofía: la paciencia es parte de la estrategia",
        [
            "La metodología de trading de ApexQuant se fundamenta en la paciencia, la disciplina y la selección cuidadosa de oportunidades. Nuestro objetivo no es operar constantemente, sino esperar a que el mercado presente las condiciones necesarias para ejecutar una operación conforme a nuestro análisis y plan de trading.",
            "En los mercados financieros, estar siempre dentro de una operación no significa estar haciendo las cosas bien. En ocasiones, la mejor decisión es permanecer fuera del mercado y esperar.",
            "Por este motivo, pueden transcurrir uno o varios días sin que se abra una nueva operación. Esto no significa necesariamente que exista un problema con la estrategia, que el sistema haya dejado de funcionar o que se haya abandonado la actividad de trading. Puede ser, sencillamente, el resultado de respetar las condiciones de entrada establecidas.",
            "<b>En ApexQuant no operamos por obligación, aburrimiento ni impaciencia. Operamos cuando identificamos una oportunidad que cumple nuestros criterios.</b>",
        ],
    ),
    (
        "2. ¿Por qué podemos pasar días sin abrir operaciones?",
        [
            "El precio de un activo financiero no siempre alcanza las zonas que consideramos óptimas para entrar al mercado.",
            "Nuestra metodología contempla esperar a que el precio llegue a una zona previamente identificada y que la operación ofrezca una estructura de entrada coherente con nuestro análisis y nuestra gestión del riesgo.",
            "En ocasiones, el precio puede acercarse mucho a la zona prevista, quedarse a pocos puntos o pips de activar una orden pendiente y, posteriormente, cambiar de dirección sin llegar a ejecutarla.",
            "Cuando esto ocurre, podemos perder esa oportunidad concreta. Sin embargo, preferimos aceptar que una operación no se haya ejecutado antes que entrar en una zona que no cumple nuestros requisitos.",
            "No perseguimos el precio ni modificamos arbitrariamente nuestro plan por miedo a quedarnos fuera de un movimiento.",
            "<b>Una oportunidad que se escapa no constituye una pérdida económica por sí misma. Una entrada ejecutada sin cumplir el plan sí puede exponer el capital a un riesgo innecesario.</b>",
        ],
    ),
    (
        "3. Las órdenes pendientes y las oportunidades que no se activan",
        [
            "Cuando las condiciones del mercado lo permiten, podemos utilizar órdenes pendientes para buscar una entrada en una zona determinada.",
            "Estas órdenes no garantizan que el precio vaya a alcanzarlas, que se ejecuten ni que el mercado se comporte como esperamos.",
            "El precio puede llegar a pocos puntos de la orden y marcharse en la dirección prevista sin activar la entrada. También puede activar la orden y moverse posteriormente en nuestra contra.",
            "Ambas situaciones forman parte de la realidad del trading.",
            "No perseguiremos automáticamente una operación perdida ni entraremos tarde únicamente porque el mercado haya comenzado a moverse. Cualquier nueva entrada deberá evaluarse conforme a los criterios de la metodología.",
            "La prioridad es mantener la coherencia del plan, no intentar participar en todos los movimientos del mercado.",
        ],
    ),
    (
        "4. Gestión del riesgo y protección del capital",
        [
            "La gestión del riesgo es un componente esencial de la metodología de ApexQuant.",
            "Toda operación conlleva la posibilidad de sufrir pérdidas, incluso cuando el análisis se ha realizado correctamente y la entrada cumple los criterios establecidos.",
            "Por ello, las operaciones deben contar con una planificación del riesgo y con niveles de salida definidos según las condiciones del mercado y la estrategia aplicada.",
            "El Stop Loss es una herramienta destinada a limitar las pérdidas potenciales, pero no garantiza que la pérdida final sea exactamente igual al importe previsto. En determinadas circunstancias, como deslizamientos de precio, gaps o condiciones excepcionales de liquidez, la ejecución puede producirse a un precio diferente del esperado.",
            "La metodología no elimina el riesgo ni garantiza la preservación del capital. Su finalidad es gestionar la exposición de forma disciplinada y evitar decisiones impulsivas que puedan comprometer innecesariamente la cuenta.",
            "<b>Preferimos dejar pasar una oportunidad antes que forzar una entrada que no cumple nuestro plan. Sin embargo, ninguna selección de entradas puede garantizar que una operación no alcance el Stop Loss.</b>",
        ],
    ),
    (
        "5. Qué debes esperar como usuario de CopyTrading",
        [
            "Al participar en ApexQuant CopyTrading, debes comprender que los resultados no se generan de manera uniforme ni necesariamente diaria.",
            "Puedes encontrar periodos en los que se abran varias operaciones y otros en los que la actividad sea reducida o inexistente durante varios días.",
            "No prometemos una cantidad mínima de operaciones, una frecuencia determinada de entradas ni beneficios diarios, semanales o mensuales.",
            "Tampoco garantizamos una rentabilidad específica, una tasa de aciertos concreta o la ausencia de periodos de pérdidas.",
            "La actividad depende de las condiciones reales del mercado y de la aparición de oportunidades que cumplan los criterios de la metodología.",
            "El CopyTrading replica operaciones conforme a las condiciones técnicas de la plataforma y de la cuenta vinculada. Pueden existir diferencias entre las operaciones del proveedor y las de la cuenta seguidora debido a factores como la ejecución, los spreads, el deslizamiento, la configuración de la cuenta, la disponibilidad de instrumentos o los requisitos del bróker.",
            "Por tanto, la frecuencia y los resultados de tu cuenta pueden diferir de los observados en otras cuentas.",
        ],
    ),
    (
        "6. Por qué no forzamos operaciones para generar actividad",
        [
            "Operar más no significa necesariamente ganar más.",
            "Abrir posiciones únicamente para mantener una actividad constante, recuperar una pérdida rápidamente o satisfacer las expectativas de quienes siguen una estrategia puede llevar a tomar decisiones fuera del plan establecido.",
            "ApexQuant prioriza la calidad de las oportunidades frente a la cantidad de operaciones.",
            "No se abrirá una operación únicamente para demostrar actividad, compensar un periodo sin entradas o intentar recuperar una pérdida anterior.",
            "Cada nueva oportunidad debe evaluarse por sus propios méritos, teniendo en cuenta el contexto del mercado y el riesgo asociado.",
            "La disciplina también consiste en saber cuándo no operar.",
        ],
    ),
    (
        "7. Expectativas, paciencia y responsabilidad del seguidor",
        [
            "Al elegir CopyTrading, debes valorar si tu horizonte temporal, tus expectativas y tu tolerancia al riesgo son compatibles con una metodología que puede permanecer varios días sin abrir operaciones.",
            "Esta estrategia puede no ser adecuada para quienes esperan movimientos constantes, operaciones diarias o resultados inmediatos.",
            "No debes interpretar la ausencia temporal de operaciones como una garantía de que se está preparando una entrada rentable. Tampoco debes considerar que una operación no ejecutada habría producido necesariamente un beneficio.",
            "El mercado puede comportarse de forma imprevisible y cualquier escenario analizado puede cambiar.",
            "Antes de vincular tu cuenta, asegúrate de comprender el funcionamiento del servicio, las condiciones de OneRoyal, las comisiones aplicables y los riesgos asociados al trading apalancado.",
            "Participa únicamente con capital que puedas permitirte perder y evita utilizar dinero destinado a gastos esenciales, obligaciones financieras o necesidades inmediatas.",
        ],
    ),
    (
        "8. Comisiones y remuneración por resultados",
        [
            "La remuneración de ApexQuant por el servicio de CopyTrading se establece conforme a las condiciones configuradas y aceptadas en la plataforma OneRoyal.",
            "Según las condiciones previstas para el servicio, ApexQuant participa con una comisión del 30 % sobre las ganancias elegibles generadas por el CopyTrading, conforme al mecanismo de cálculo y liquidación de OneRoyal.",
            "La ausencia de operaciones o de ganancias elegibles no implica que se generen beneficios por el mero hecho de mantener la cuenta vinculada. La aplicación efectiva de cualquier comisión depende de las condiciones de la plataforma y de los términos vigentes del servicio.",
            "Las condiciones particulares de tu cuenta, así como cualquier otra tarifa, coste de negociación o cargo aplicable por el bróker, deben consultarse directamente con OneRoyal antes de participar.",
        ],
    ),
    (
        "9. Aceptación de los riesgos",
        [
            "El trading de instrumentos financieros, especialmente mediante apalancamiento, implica un riesgo significativo de pérdida de capital.",
            "Los resultados pasados no garantizan resultados futuros. Una operación rentable no asegura que la siguiente también lo sea, y una metodología disciplinada no elimina las pérdidas ni garantiza una rentabilidad positiva.",
            "Al utilizar ApexQuant CopyTrading, reconoces que:\n"
            "• Pueden transcurrir varios días sin nuevas operaciones.\n"
            "• Algunas oportunidades pueden quedar sin ejecutar porque el precio no alcance la zona prevista.\n"
            "• Las operaciones ejecutadas pueden cerrar con pérdidas, incluido el Stop Loss.\n"
            "• No existe garantía de beneficios ni de recuperación de pérdidas.\n"
            "• Los resultados de tu cuenta pueden diferir de los del proveedor.\n"
            "• Eres responsable de evaluar tu situación financiera, tu tolerancia al riesgo y la conveniencia de participar.\n"
            "• Debes revisar y aceptar las condiciones aplicables de OneRoyal y de la plataforma de CopyTrading.",
            "La decisión de participar debe basarse en una comprensión realista de la metodología y de los riesgos, no en la expectativa de obtener ganancias rápidas o constantes.",
        ],
    ),
    (
        "10. Nuestro compromiso con la disciplina",
        [
            "ApexQuant se compromete a mantener una filosofía de trading basada en la paciencia, la planificación y el respeto por los criterios de entrada y gestión del riesgo de la metodología.",
            "No prometemos acertar siempre. No prometemos operar todos los días. No prometemos evitar todas las pérdidas.",
            "Nuestro compromiso es no confundir actividad con calidad, ni impaciencia con oportunidad.",
            "A veces, el mercado se moverá sin nosotros. Otras veces, una entrada válida terminará en Stop Loss. Ambas posibilidades forman parte de esta actividad.",
            "Lo importante es no permitir que el miedo a perder una oportunidad o el deseo de recuperar una pérdida dicten nuestras decisiones.",
            "<b>APEXQUANT — La paciencia no garantiza el éxito, pero operar sin disciplina puede aumentar innecesariamente el riesgo.</b>",
        ],
    ),
]

COPY_TERMS_FOOTER = (
    "<i>Este documento describe la filosofía y las expectativas generales de la "
    "metodología. No constituye una garantía de resultados ni sustituye las "
    "condiciones contractuales de OneRoyal, la documentación oficial del servicio "
    "o el asesoramiento financiero independiente que puedas necesitar.</i>"
)

COPY_TERMS_PAGE_LIMIT = 3300


def _build_copy_terms_pages(limit=COPY_TERMS_PAGE_LIMIT):
    """Agrupa secciones/párrafos completos en páginas que caben en un mensaje."""
    units = []
    for title, paragraphs in COPY_TERMS_SECTIONS:
        heading = "<b>" + title + "</b>"
        section_text = heading + "\n\n" + "\n\n".join(paragraphs)
        if len(section_text) <= limit:
            units.append(section_text)
            continue
        current = heading
        for paragraph in paragraphs:
            candidate = current + "\n\n" + paragraph
            if len(candidate) > limit and current != heading:
                units.append(current)
                current = paragraph
            else:
                current = candidate
        units.append(current)
    units.append(COPY_TERMS_FOOTER)

    pages = []
    current = ""
    for unit in units:
        candidate = unit if not current else current + "\n\n" + unit
        if current and len(candidate) > limit:
            pages.append(current)
            current = unit
        else:
            current = candidate
    if current:
        pages.append(current)
    return pages


COPY_TERMS_PAGES = _build_copy_terms_pages()


def copy_terms_keyboard(page):
    total = len(COPY_TERMS_PAGES)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"copy_terms_p_{page - 1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"copy_terms_p_{page + 1}"))
    keyboard = []
    if nav:
        keyboard.append(nav)
    if page == total - 1:
        keyboard.append([InlineKeyboardButton("✅ He leído los términos", callback_data="copy_terms_read")])
    keyboard.append([InlineKeyboardButton("🔙 Volver a CopyTrading", callback_data="copytrading")])
    return InlineKeyboardMarkup(keyboard)


async def show_copy_terms(query, page=0):
    total = len(COPY_TERMS_PAGES)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    page = max(0, min(page, total - 1))
    text = (
        "📜 <b>" + COPY_TERMS_TITLE + "</b>\n"
        f"<i>Página {page + 1} de {total}</i>\n\n"
        + COPY_TERMS_PAGES[page]
    )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=copy_terms_keyboard(page)
    )


def copytrading_menu():

    keyboard = []

    # --------------------------------------------------------
    # TÉRMINOS Y CONDICIONES (siempre el primer botón)
    # --------------------------------------------------------

    keyboard.append([
        InlineKeyboardButton(
            "📜 TÉRMINOS Y CONDICIONES",
            callback_data="copy_terms"
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
        "📋 <b>COPYTRADING — APEXQUANT</b>\n\n"
        "Sigue la estrategia ApexQuant desde tu propia cuenta de OneRoyal.\n\n"
        "🧭 <b>Cómo empezar</b>\n"
        "1️⃣ Regístrate en OneRoyal con el enlace IB de ApexQuant.\n"
        "2️⃣ Completa la verificación de identidad y abre una cuenta compatible.\n"
        "3️⃣ Abre el enlace de Social Trading y suscríbete a ApexQuant.\n"
        "4️⃣ Revisa la cuenta MT5 solicitada y configura el riesgo disponible.\n\n"
        "💰 <b>Distribución de las ganancias</b>\n"
        "Según el esquema de rendimiento anunciado por ApexQuant, de las ganancias "
        "sujetas a comisión, el 70% corresponde al usuario y el 30% a ApexQuant. "
        "La aplicación efectiva depende de que la oferta de OneRoyal muestre y permita "
        "esa configuración. No es una garantía de beneficio: también puedes perder capital.\n\n"
        "✅ ApexQuant no cobra cuota de entrada ni cuota fija de gestión. Si no hay "
        "ganancias sujetas a comisión, no se genera comisión de rendimiento.\n\n"
        "🌎 Comprueba que OneRoyal y el CopyTrading estén disponibles en tu país antes "
        "de registrarte o depositar fondos.\n\n"
        "⚠️ El trading con apalancamiento implica riesgo de pérdida. Los resultados "
        "pasados no garantizan resultados futuros."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=copytrading_menu())


async def show_copy_info(query):
    text = (
        "ℹ️ <b>¿CÓMO FUNCIONA EL COPYTRADING?</b>\n\n"
        "• Las operaciones de la estrategia pueden replicarse en tu cuenta, según "
        "la plataforma y la configuración elegida.\n"
        "• Tú mantienes tu cuenta y eres responsable de revisar el capital, exposición "
        "y parámetros de riesgo.\n\n"
        "💰 <b>Reparto de rendimiento de ApexQuant</b>\n"
        "El esquema previsto es 70% de las ganancias sujetas a comisión para el usuario "
        "y 30% para ApexQuant. Confirma que las condiciones visibles en OneRoyal "
        "coincidan antes de suscribirte.\n\n"
        "ApexQuant no cobra cuota de entrada ni cuota fija de gestión. Si no existen "
        "ganancias sujetas a comisión, no se genera comisión de rendimiento.\n\n"
        "⚠️ No hay beneficios garantizados. Puedes perder parte o todo el capital. "
        "Los resultados pasados no garantizan resultados futuros."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=copytrading_menu())


async def show_copy_follow(query):
    await show_copy_info(query)


async def show_copy_register(query):
    text = (
        "📝 <b>REGISTRO EN ONEROYAL</b>\n\n"
        "1️⃣ Pulsa «Abrir cuenta OneRoyal» y completa el registro con el enlace IB de ApexQuant.\n"
        "2️⃣ Completa la verificación de identidad que solicite el broker.\n"
        "3️⃣ Comprueba con OneRoyal qué tipo de cuenta y plataforma son compatibles.\n"
        "4️⃣ Después pulsa «Seguir Apex Quant» para abrir el enlace de Social Trading.\n"
        "5️⃣ Revisa la oferta, las comisiones y el riesgo antes de confirmar la suscripción.\n\n"
        "⚠️ La disponibilidad y los requisitos dependen del país y de las condiciones vigentes."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=copytrading_menu())


async def show_copy_steps(query):
    await show_copy_register(query)


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
        "OneRoyal ofrece acceso a mercados de Forex y CFD, incluidos metales, índices, "
        "energía, acciones y criptomonedas, según la entidad y el país. También ofrece "
        "plataformas MT4/MT5, herramientas de trading y CopyTrading.\n\n"
        "🛡️ <b>Regulación y entidad</b>\n"
        "El grupo opera mediante distintas entidades. La información pública de OneRoyal "
        "menciona ASIC (Australia), CySEC (Chipre), VFSC (Vanuatu) y FSA de San Vicente "
        "y las Granadinas para entidades distintas. La protección legal depende de la "
        "entidad con la que se abra la cuenta; no todas las licencias aplican a todos los clientes.\n\n"
        "📊 <b>Cuentas ECN — opción destacada</b>\n"
        "La cuenta ECN anuncia spreads brutos desde 0.0 pips y comisión separada. En la "
        "página internacional consultada, la referencia publicada es USD 3.50 por lado "
        "por lote (USD 7 ida y vuelta por lote estándar). El spread es variable y puede "
        "ampliarse según liquidez, volatilidad e instrumento.\n\n"
        "💵 <b>Comparación orientativa</b>\n"
        "• ECN: spread desde 0.0 pips + comisión.\n"
        "• Classic: comisión anunciada de USD 0 y spread desde 1.4 pips en la página internacional.\n"
        "Los depósitos mínimos, tarifas, apalancamiento y tipos de cuenta pueden variar por país, "
        "entidad, plataforma y proveedor de pago. Confirma siempre las condiciones que aparecen "
        "en tu portal antes de depositar.\n\n"
        "🧰 <b>Características anunciadas</b>\n"
        "MT4/MT5, operaciones desde 0.01 lotes, asesores expertos y cobertura de saldo negativo "
        "en cuentas/entidades donde corresponda; más de 2,000 instrumentos según la oferta publicada.\n\n"
        "👇 Consulta también la información del bono tradeable.\n\n"
        "⚠️ El apalancamiento puede aumentar las pérdidas. Verifica disponibilidad regional, "
        "costes y documentación legal de tu entidad."
    )
    keyboard = []
    if ONEROYAL_IB_URL:
        keyboard.append([InlineKeyboardButton("🚀 Registrarme con OneRoyal", url=ONEROYAL_IB_URL)])
    else:
        keyboard.append([InlineKeyboardButton("⚠️ Enlace OneRoyal no configurado", callback_data="ib_link_missing")])
    keyboard.append([InlineKeyboardButton("🎁 Información del bono tradeable", callback_data="broker_bonus")])
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data="back_main")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)


async def show_broker_bonus(query):
    text = (
        "🎁 <b>BONO TRADEABLE ONEROYAL</b>\n\n"
        "Según la explicación compartida por el manager de OneRoyal, el cliente debe "
        "registrarse y completar la verificación de identidad. Se indicó que la verificación "
        "inteligente puede solicitar una foto del documento y una selfie, si el portal la ofrece.\n\n"
        "🧾 <b>Activación explicada por el manager</b>\n"
        "1️⃣ Después de verificar la cuenta, entra al menú del cliente y abre la sección de bonos.\n"
        "2️⃣ Lee y acepta los términos y condiciones del bono.\n"
        "3️⃣ Selecciona un tipo de cuenta elegible; el manager mencionó cuentas Standard y ECN con bono.\n"
        "4️⃣ Al elegir la cuenta y depositar, el bono aplicable se refleja según las condiciones de la promoción.\n\n"
        "💵 <b>Ejemplos compartidos por el manager</b>\n"
        "• Depósito de USD 300: ejemplo de bono de USD 300.\n"
        "• Depósito de USD 1,000: ejemplo de bono de USD 500.\n\n"
        "⚠️ <b>Importante sobre el bono</b>\n"
        "El manager indicó que el bono no es retirable, mientras que las ganancias generadas "
        "pueden ser retirables, sujeto a los términos. El bono puede servir como margen adicional "
        "y puede retirarse/cancelarse si se retira depósito o equity, según las reglas aplicables. "
        "Los ejemplos anteriores no son una oferta universal ni garantizan elegibilidad: el importe, "
        "cuentas admitidas, vigencia y condiciones dependen de la promoción, país y entidad.\n\n"
        "Antes de depositar, abre y lee los términos oficiales vigentes en tu portal y confirma "
        "con OneRoyal si retirar fondos afecta el bono o las ganancias. No deposites solo por el bono."
    )
    keyboard = []
    if ONEROYAL_IB_URL:
        keyboard.append([InlineKeyboardButton("🏦 Registrarme con OneRoyal", url=ONEROYAL_IB_URL)])
    keyboard.append([InlineKeyboardButton("🔙 Volver a OneRoyal", callback_data="broker_oneroyal")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)


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

WEEKDAYS_ES = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def date_label_es(day):
    return f"{WEEKDAYS_ES[day.weekday()]} {day:%d/%m}"


def today_date():
    # Fecha de hoy en la zona horaria configurada (no la del servidor).
    return datetime.now(CALENDAR_TZ).date()


def tomorrow_date():
    return today_date() + timedelta(days=1)


def week_dates():
    start = today_date()
    end = start + timedelta(days=6)

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
                "🔴 Alto",
                callback_data="calendar_high"
            ),
            InlineKeyboardButton(
                "🟠 Medio",
                callback_data="calendar_medium"
            ),
            InlineKeyboardButton(
                "🟢 Bajo",
                callback_data="calendar_low"
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

CALENDAR_FETCH_CACHE = {}


def _parse_iso_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def event_datetime_utc(event):
    """Instante exacto de publicación en UTC, o None si el evento sólo tiene fecha."""

    if not isinstance(event, dict):
        return None

    parsed = _parse_iso_datetime(
        event.get("release_at_utc") or event.get("time_utc")
    )

    return parsed.astimezone(timezone.utc) if parsed else None


def event_local_date(event):
    """Fecha del evento en la zona horaria del bot."""

    moment = event_datetime_utc(event)

    if moment:
        return moment.astimezone(CALENDAR_TZ).date()

    raw = str(event.get("date") or "")[:10]

    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def event_sort_key(event):
    moment = event_datetime_utc(event)

    if moment:
        local = moment.astimezone(CALENDAR_TZ).replace(tzinfo=None)
    else:
        day = event_local_date(event) or date.max
        local = datetime.combine(day, datetime.min.time())

    return (local, str(event.get("name") or ""))


def is_economic_event(event):
    """Descarta eventos cripto, subastas (opcional) y filas sin datos útiles."""

    if not isinstance(event, dict):
        return False

    category = str(event.get("category") or "").lower()

    if "crypto" in category or category == "market-holidays":
        return False

    series_code = str(event.get("series_code") or "").lower()
    impact = str(event.get("impact") or "").lower()

    if (
        not CALENDAR_SHOW_AUCTIONS
        and series_code.startswith("us-treasury")
        and impact != "high"
    ):
        return False

    if category in CALENDAR_CATEGORIES:
        return True

    # Sin categoría: sólo se acepta si parece un evento económico real.
    return impact in ("high", "medium", "low") and bool(event_currency(event))


def _fc_request(params):
    url = FINANCE_CALENDAR_BASE + "/calendar?" + urlencode(params)

    headers = {
        "User-Agent": "Mozilla/5.0 ApexQuantBot/1.0",
        "Accept": "application/json"
    }

    if FINANCE_CALENDAR_API_KEY:
        headers["X-API-Key"] = FINANCE_CALENDAR_API_KEY

    request = Request(url, headers=headers)

    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _fc_collect(params):
    """Descarga todas las páginas de una consulta (máx. 500 filas por página)."""

    rows = []
    offset = 0

    for _ in range(6):
        data = _fc_request(dict(params, limit=500, offset=offset))

        if isinstance(data, dict):
            page = data.get("events")
            if not isinstance(page, list):
                page = data.get("data") if isinstance(data.get("data"), list) else []
            total = data.get("total")
        elif isinstance(data, list):
            page = data
            total = None
        else:
            break

        rows.extend(page)
        offset += len(page)

        try:
            total = int(total) if total is not None else None
        except (TypeError, ValueError):
            total = None

        if not page or total is None or offset >= total:
            break

    return rows


def _fc_load(start_date, end_date, impact=None):
    base = {
        "from": start_date.strftime("%Y-%m-%d"),
        "to": end_date.strftime("%Y-%m-%d"),
        "tz": CALENDAR_TZ_LABEL
    }

    if impact:
        base["impact"] = impact

    rows = []

    try:
        for category in CALENDAR_CATEGORIES:
            rows.extend(_fc_collect(dict(base, category=category)))
    except Exception as error:
        logger.warning(
            "FinanceCalendar: falló la consulta por categoría (%s). "
            "Se reintenta sin filtro y se limpian los eventos aquí.",
            error
        )
        rows = _fc_collect(base)

    unique = []
    seen = set()

    for event in rows:
        if not is_economic_event(event):
            continue

        key = str(event.get("id") or "") or "|".join(
            str(event.get(k) or "") for k in ("name", "date", "time_utc")
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(event)

    return unique


def _fc_load_with_retry(start_date, end_date, impact=None):
    last_error = None

    for attempt in range(2):
        try:
            return _fc_load(start_date, end_date, impact)
        except Exception as error:
            last_error = error
            if attempt == 0:
                time.sleep(1.0)

    raise last_error


async def fetch_calendar_events(start_date, end_date=None, impact=None):
    """Eventos económicos entre dos fechas (en la zona horaria del bot).

    Devuelve una lista ordenada por hora, o None si FinanceCalendar no responde.
    """

    if end_date is None:
        end_date = start_date

    cache_key = (start_date.isoformat(), end_date.isoformat(), impact or "")
    cached = CALENDAR_FETCH_CACHE.get(cache_key)

    if cached and time.monotonic() - cached[0] < CALENDAR_CACHE_SECONDS:
        return list(cached[1])

    loop = asyncio.get_running_loop()

    try:
        # Se pide un día de margen a cada lado porque la API filtra por la fecha
        # local de quien publica y aquí se necesita la fecha en la zona del bot.
        rows = await loop.run_in_executor(
            None,
            _fc_load_with_retry,
            start_date - timedelta(days=1),
            end_date + timedelta(days=1),
            impact
        )
    except HTTPError as error:
        logger.error("Error obteniendo calendario: HTTP %s", error.code)
        return list(cached[1]) if cached else None
    except Exception as error:
        logger.error("Error obteniendo calendario: %s", error)
        return list(cached[1]) if cached else None

    events = []

    for event in rows:
        day = event_local_date(event)

        if day and start_date <= day <= end_date:
            events.append(event)

    events.sort(key=event_sort_key)

    CALENDAR_FETCH_CACHE[cache_key] = (time.monotonic(), events)

    if len(CALENDAR_FETCH_CACHE) > 40:
        oldest = min(CALENDAR_FETCH_CACHE, key=lambda k: CALENDAR_FETCH_CACHE[k][0])
        CALENDAR_FETCH_CACHE.pop(oldest, None)

    return list(events)


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
        "country_name",
        "region",
        "market",
        "location",
        "geo",
        "area",
        "zone",
        "flag"
    )

    country_text = str(country or "").upper().strip()

    country_map = {
        "US": "USD", "USA": "USD", "UNITED STATES": "USD",
        "EU": "EUR", "EUROZONE": "EUR", "EURO AREA": "EUR",
        "GERMANY": "EUR", "DE": "EUR", "FRANCE": "EUR", "ITALY": "EUR",
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

    # Variantes de nombre de país (p. ej. "United States of America", "Euro Zone").
    if country_text:
        country_norm = " " + re.sub(r"[^A-Z0-9]+", " ", country_text).strip() + " "
        for key, code in country_map.items():
            if len(key) > 2 and f" {key} " in country_norm:
                return code

    # 3) País/divisa implícito en el nombre, título, URL o descripción.
    #    Se normaliza el texto (todo lo que no sea letra/número pasa a espacio)
    #    para que "us-retail-sales", "TSE/JPX" o "U.S." también coincidan,
    #    y se busca por PALABRA COMPLETA para evitar falsos positivos.
    name = str(event_value(event, "name", "title", "event") or "")
    url = str(event_value(event, "url", "link", "slug") or "")
    extra = str(event_value(event, "description", "source", "category", "unit") or "")
    raw_text = f"{name} {url} {extra}".upper()
    haystack = " " + re.sub(r"[^A-Z0-9]+", " ", raw_text).strip() + " "

    keyword_map = [
        # Países/regiones con nombre explícito primero (más fiable)
        (("EUROZONE", "EURO ZONE", "EURO AREA", "EUROPEAN CENTRAL BANK", "ECB",
          "EUROPEAN UNION", "EUROPE", "ZEW", "IFO", "GERMANY", "GERMAN", "FRANCE",
          "FRENCH", "ITALY", "ITALIAN", "SPAIN", "SPANISH", "EUREX", "DAX", "EURONEXT"), "EUR"),
        (("UNITED KINGDOM", "UK", "U K", "BRITAIN", "BRITISH", "BOE", "BANK OF ENGLAND",
          "LONDON", "LSE", "FTSE", "SONIA"), "GBP"),
        (("JAPAN", "JAPANESE", "BOJ", "BANK OF JAPAN", "TOKYO", "TSE", "JPX",
          "NIKKEI", "TANKAN"), "JPY"),
        (("SWITZERLAND", "SWISS", "SNB", "SWISS NATIONAL BANK", "ZURICH", "SIX"), "CHF"),
        (("CANADA", "CANADIAN", "BOC", "BANK OF CANADA", "TORONTO", "TSX", "IVEY"), "CAD"),
        (("AUSTRALIA", "AUSTRALIAN", "RBA", "RESERVE BANK OF AUSTRALIA", "SYDNEY", "ASX"), "AUD"),
        (("NEW ZEALAND", "RBNZ", "RESERVE BANK OF NEW ZEALAND", "AUCKLAND", "NZX"), "NZD"),
        (("CHINA", "CHINESE", "PBOC", "PEOPLE S BANK OF CHINA", "CAIXIN", "SHANGHAI",
          "SHENZHEN", "NBS"), "CNY"),
        (("HONG KONG", "HKEX", "HKMA"), "HKD"),
        (("SINGAPORE", "MAS", "SGX"), "SGD"),
        (("SWEDEN", "SWEDISH", "RIKSBANK"), "SEK"),
        (("NORWAY", "NORWEGIAN", "NORGES BANK"), "NOK"),
        (("MEXICO", "MEXICAN", "BANXICO"), "MXN"),
        (("BRAZIL", "BRAZILIAN", "BCB"), "BRL"),
        (("INDIA", "INDIAN", "RBI"), "INR"),
        (("SOUTH KOREA", "KOREA", "KOREAN", "BOK"), "KRW"),
        (("SOUTH AFRICA", "SARB"), "ZAR"),
        # USD al final: "US" es una palabra corta y puede aparecer en otros contextos
        (("USA", "UNITED STATES", "AMERICAN", "FED", "FOMC", "FEDERAL RESERVE",
          "TREASURY", "JOBLESS CLAIMS", "NON FARM", "NONFARM", "NFP", "PAYROLL", "ADP",
          "ISM", "PCE", "BEIGE BOOK", "NYSE", "NASDAQ", "SIFMA", "WALL STREET",
          "COLUMBUS DAY", "JUNETEENTH", "S P GLOBAL", "MICHIGAN", "CONFERENCE BOARD",
          "EMPIRE STATE", "PHILLY FED", "DALLAS FED", "CHICAGO PMI"), "USD"),
    ]

    for keywords, code in keyword_map:
        if any(f" {keyword} " in haystack for keyword in keywords):
            return code

    # "US" / "U.S." solo cuenta si va en mayúsculas en el título (evita el pronombre "us"),
    # o como palabra suelta en la URL (p. ej. /us-retail-sales).
    if re.search(r"(?<![A-Za-z])U\.?S\.?(?![A-Za-z])", name) or \
            re.search(r"(?<![a-z])us(?![a-z])", url.lower()):
        return "USD"

    # 4) Sin pistas suficientes: se deja registro (una vez por evento) para poder
    #    ver qué campos entrega el feed y afinar la detección.
    try:
        marker = name or str(event.get("id", ""))
        if marker and marker not in _UNRESOLVED_CURRENCY_LOGGED:
            if len(_UNRESOLVED_CURRENCY_LOGGED) > 200:
                _UNRESOLVED_CURRENCY_LOGGED.clear()
            _UNRESOLVED_CURRENCY_LOGGED.add(marker)
            logger.info(
                "Divisa no resuelta | nombre=%r | campos=%s | url=%r",
                name[:80], sorted(event.keys()), url[:120]
            )
    except Exception:
        pass

    return ""


_UNRESOLVED_CURRENCY_LOGGED = set()


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

def event_time_text(event):

    moment = event_datetime_utc(event)

    if moment:
        local = moment.astimezone(CALENDAR_TZ)
        return f"{date_label_es(local.date())} · {local:%H:%M}"

    day = event_local_date(event)

    if day:
        return f"{date_label_es(day)} · hora por confirmar"

    return "Hora no disponible"


def format_calendar_event(event):

    name = str(event_value(event, "name", "title", "event") or "Evento económico")
    if len(name) > 110:
        name = name[:107] + "..."

    currency = event_currency(event)
    impact = event_value(event, "impact", "importance")
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

    status = str(event.get("status") or "").lower()
    status_text = (
        " · 🗓️ fecha estimada"
        if status in ("estimated", "rescheduled") else ""
    )

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
        f"📰 {escape(name)}\n"
        f"🕒 {escape(event_time_text(event))}{status_text}"
        f"{result_text}"
    )


# ============================================================
# MOSTRAR EVENTOS
# ============================================================

async def _calendar_edit(query, text, keyboard):
    try:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except BadRequest as error:
        # Pulsar "Actualizar" sin cambios en los datos no es un error.
        if "not modified" in str(error).lower():
            return
        raise


async def show_events(
    query,
    start_date,
    end_date=None,
    title="📅 CALENDARIO",
    filter_impact=None,
    currency=None,
    page=0,
    mode=None
):

    events = await fetch_calendar_events(
        start_date,
        end_date,
        impact=filter_impact
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
                    callback_data=(
                        f"calpage_{mode}_{page}" if mode else "calendar"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Volver",
                    callback_data="calendar"
                )
            ]
        ]

        await _calendar_edit(query, text, keyboard)

        return

    filtered_events = []

    for event in events:

        if not isinstance(event, dict):
            continue

        if filter_impact:
            impact = str(
                event_value(event, "impact", "importance")
            ).lower()

            if impact != filter_impact:
                continue

        if currency and event_currency(event) != currency.upper():
            continue

        filtered_events.append(event)

    # Los eventos ya vienen ordenados por hora local desde fetch_calendar_events.

    total = len(filtered_events)
    pages = max(1, (total + CALENDAR_PAGE_SIZE - 1) // CALENDAR_PAGE_SIZE)

    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0

    page = max(0, min(page, pages - 1))

    page_events = filtered_events[
        page * CALENDAR_PAGE_SIZE:(page + 1) * CALENDAR_PAGE_SIZE
    ]

    header = (
        f"{title}\n"
        f"🕒 <i>Horas en {escape(CALENDAR_TZ_LABEL)}</i>"
    )

    footer = (
        '\n\nℹ️ Fuente: <a href="https://www.financecalendar.com">'
        "FinanceCalendar.com</a>"
    )

    keyboard = []

    if not page_events:
        text = (
            f"{header}\n\n"
            "📭 <b>No hay eventos disponibles "
            "para los filtros seleccionados.</b>\n\n"
            "Puedes actualizar o consultar otra fecha/divisa."
            f"{footer}"
        )
    else:
        event_texts = []

        for event in page_events:
            event_key = cache_calendar_event(event)
            event_texts.append(format_calendar_event(event))

            short_name = str(
                event_value(event, "name", "title", "event") or "Evento"
            )
            if len(short_name) > 30:
                short_name = short_name[:27] + "..."

            event_cur = event_currency(event)
            prefix = f"{event_cur} · " if event_cur else ""

            keyboard.append([
                InlineKeyboardButton(
                    f"📚 {prefix}{short_name}",
                    callback_data=f"calendar_context_{event_key}"
                )
            ])

        page_info = (
            f"\n\n📄 Página {page + 1}/{pages} · {total} eventos"
            if pages > 1 else f"\n\n📄 {total} eventos"
        )

        text = (
            f"{header}\n\n"
            + "\n\n".join(event_texts)
            + page_info
            + footer
        )

    if mode and pages > 1:
        nav = []

        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    "⬅️ Anterior",
                    callback_data=f"calpage_{mode}_{page - 1}"
                )
            )

        if page < pages - 1:
            nav.append(
                InlineKeyboardButton(
                    "Siguiente ➡️",
                    callback_data=f"calpage_{mode}_{page + 1}"
                )
            )

        if nav:
            keyboard.append(nav)

    keyboard.extend([
        [
            InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data=(
                    f"calpage_{mode}_{page}" if mode else "calendar"
                )
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Calendario",
                callback_data="calendar"
            )
        ]
    ])

    await _calendar_edit(query, text[:4000], keyboard)


async def show_calendar_mode(query, mode, page=0):
    """Dibuja una vista del calendario (hoy, mañana, semana, impacto, divisa)."""

    mode = str(mode or "")

    if mode == "today":
        day = today_date()
        await show_events(
            query, day, day,
            title=f"📅 <b>EVENTOS DE HOY</b> — {date_label_es(day)}",
            page=page, mode=mode
        )

    elif mode == "tomorrow":
        day = tomorrow_date()
        await show_events(
            query, day, day,
            title=f"📅 <b>EVENTOS DE MAÑANA</b> — {date_label_es(day)}",
            page=page, mode=mode
        )

    elif mode == "week":
        start, end = week_dates()
        await show_events(
            query, start, end,
            title=(
                "📆 <b>EVENTOS DE ESTA SEMANA</b>\n"
                f"📅 {date_label_es(start)} → {date_label_es(end)}"
            ),
            page=page, mode=mode
        )

    elif mode in ("high", "medium", "low"):
        start, end = week_dates()
        icon, label = {
            "high": ("🔴", "ALTO"),
            "medium": ("🟠", "MEDIO"),
            "low": ("🟢", "BAJO")
        }[mode]
        await show_events(
            query, start, end,
            title=(
                f"{icon} <b>EVENTOS DE IMPACTO {label}</b>\n"
                f"📅 {date_label_es(start)} → {date_label_es(end)}"
            ),
            filter_impact=mode,
            page=page, mode=mode
        )

    elif mode.startswith("cur_"):
        currency = mode[4:].upper()
        start, end = week_dates()
        flag = CALENDAR_CURRENCY_FLAGS.get(currency, "💵")
        await show_events(
            query, start, end,
            title=f"{flag} <b>EVENTOS {escape(currency)}</b>",
            currency=currency,
            page=page, mode=mode
        )

    else:
        await calendar_menu(query)


# ============================================================
# CALENDARIO - HOY / MAÑANA / SEMANA / IMPACTO
# ============================================================

async def show_calendar_today(query):
    await show_calendar_mode(query, "today")


async def show_calendar_tomorrow(query):
    await show_calendar_mode(query, "tomorrow")


async def show_calendar_week(query):
    await show_calendar_mode(query, "week")


async def show_calendar_high(query):
    await show_calendar_mode(query, "high")


async def show_calendar_medium(query):
    await show_calendar_mode(query, "medium")


async def show_calendar_low(query):
    await show_calendar_mode(query, "low")


async def show_calendar_page(query, payload):
    """callback_data: calpage_<modo>_<página> (el modo puede contener '_')."""

    mode, _, page_text = str(payload).rpartition("_")

    try:
        page = int(page_text)
    except ValueError:
        mode, page = str(payload), 0

    await show_calendar_mode(query, mode, page)


# ============================================================
# CALENDARIO - SELECCIÓN DE DIVISA
# ============================================================

async def currency_events(query):

    start_date, end_date = week_dates()
    events = await fetch_calendar_events(start_date, end_date)

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
        flag = CALENDAR_CURRENCY_FLAGS.get(currency, "💵")
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
            "eventos disponibles durante los próximos 7 días.\n\n"
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

    await _calendar_edit(query, text, keyboard)


async def show_currency_events(
    query,
    currency
):

    await show_calendar_mode(query, f"cur_{str(currency).upper()}")


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
        "Sigue estos pasos en orden. Las comisiones, atribución y condiciones "
        "dependen de OneRoyal y de la configuración que apruebe.\n\n"
        "1️⃣ <b>Registro con el link IB de ApexQuant</b>\n"
        "Regístrate en OneRoyal con el botón <b>Registrarme con OneRoyal</b> y verifica "
        "tu cuenta. Así quedas como cliente directo de ApexQuant; es la base de todo "
        "lo demás.\n\n"
        "2️⃣ <b>Cuenta ECN principal (fondeada)</b>\n"
        "En el menú <b>Cuentas</b> de OneRoyal crea una cuenta ECN. En ella depositas "
        "fondos para operar o para el CopyTrading, conectándote con el enlace de "
        "proveedor (botón <b>Seguir Apex Quant</b>).\n\n"
        "3️⃣ <b>Solicita ser IB</b>\n"
        "Si quieres ser agente adicional (Sub-IB) de ApexQuant, solicita a soporte de "
        "OneRoyal (por e-mail o soporte interno) convertirte también en IB desde tu "
        "cuenta. Es necesario antes de pedir el enlace de agente.\n\n"
        "4️⃣ <b>Segunda cuenta ECN (para tus comisiones)</b>\n"
        "Ya como IB, crea en <b>Cuentas</b> una segunda cuenta ECN, aparte de la "
        "fondeada que participa en el CopyTrading. En esa segunda cuenta recibirás el "
        "performance fee de tus clientes directos.\n\n"
        "5️⃣ <b>Contacta al administrador</b>\n"
        "Con los pasos anteriores completos, pulsa <b>Contactar al manager de "
        "ApexQuant</b> y solicita tu enlace de agente (agente adicional/público). "
        "Envía por ese canal privado el <b>número de tu segunda cuenta ECN</b>. "
        "El administrador crea manualmente tu enlace, lo asocia a esa cuenta y "
        "configura la comisión en la campaña; el bot no lo hace automáticamente. "
        "Nunca envíes contraseñas ni códigos de acceso, ni datos en grupos públicos.\n\n"
        "💵 <b>Participación del agente</b>\n"
        "Recibes el 20% de la parte de comisión que corresponde a ApexQuant, según la "
        "configuración acordada; no es el 20% de las ganancias totales del seguidor. "
        "Ejemplo: si ApexQuant recibe el 30% de una base sujeta a comisión, tu 20% "
        "equivale al 6% de esa base.\n\n"
        "ℹ️ <b>Sub-IB y Public Agent:</b> Sub-IB pertenece a la estructura de IB de "
        "OneRoyal; Public Agent corresponde a ofertas de CopyTrading, donde el agente "
        "puede recibir parte de las fees configuradas en la oferta.\n\n"
        "❓ <b>¿Dudas?</b> Contacta al administrador de ApexQuant con el botón de abajo.\n\n"
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
        [InlineKeyboardButton("📣 Mensaje a usuarios", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🧭 Alertas técnicas", callback_data="admin_tech")],
        [InlineKeyboardButton("📊 Estado de publicaciones", callback_data="admin_community_stats")],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]
    ])


async def show_admin_menu(query):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return
    channel_status = "🟢 Canal conectado" if get_community_channel_id() else "🟡 Canal pendiente de detección"
    text = ("🛠️ <b>ADMINISTRACIÓN — COMUNIDAD</b>\n\n" f"{channel_status}\n" f"📅 Publicaciones manuales hoy: <b>{community_post_count()}/{COMMUNITY_DAILY_TARGET}</b>\n\n" "📢 Desde aquí puedes mantener activa la Comunidad con publicaciones manuales.\n\n" "🚨 Las alertas automáticas (eventos de alto y medio impacto y alertas técnicas) funcionan por separado y no consumen el objetivo de 3 publicaciones manuales.")
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
    await query.edit_message_text("📊 <b>ESTADO DE COMUNIDAD</b>\n\n" f"📅 Publicaciones manuales hoy: <b>{community_post_count()}/{COMMUNITY_DAILY_TARGET}</b>\n" f"📢 Canal: <code>{get_community_channel_id() or 'Pendiente de detección'}</code>\n\n" "🚨 Las alertas automáticas de eventos (alto y medio impacto) y las alertas técnicas son independientes.",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Administración",callback_data="admin_menu")]]))


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not is_admin(update.effective_user.id): return
    context.user_data.pop("admin_action",None)
    context.user_data.pop("broadcast_draft",None)
    await update.message.reply_text("❌ Cancelado. No se ha enviado nada.",reply_markup=admin_menu_keyboard())


async def admin_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post or not update.message or not update.effective_user or not is_admin(update.effective_user.id): return
    admin_action=context.user_data.get("admin_action")
    if admin_action == "broadcast_text":
        await admin_broadcast_receive_text(update, context)
        return
    if admin_action != "community_text": return
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


# ============================================================
# ADMINISTRACIÓN — MENSAJES A LOS USUARIOS DEL BOT
# ============================================================

BROADCAST_HEADER_HTML = "📢 <b>Aviso de ApexQuant</b>\n\n"
BROADCAST_HEADER_PLAIN = "📢 Aviso de ApexQuant\n\n"
BROADCAST_MAX_CHARS = 3500
_BROADCAST_TASKS = set()


def broadcast_recipient_ids():
    """Usuarios que han aceptado los términos (es decir, que usan el bot)."""

    ids = []

    for raw_id in load_consents().keys():
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    return ids


def broadcast_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back_main")]
    ])


async def admin_broadcast_prompt(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return

    context.user_data.pop("broadcast_draft", None)
    context.user_data["admin_action"] = "broadcast_text"

    total = len(broadcast_recipient_ids())

    await query.edit_message_text(
        "📣 <b>MENSAJE A USUARIOS</b>\n\n"
        f"Escribe ahora el mensaje que quieres enviar desde el bot a todos "
        f"los usuarios registrados (<b>{total}</b>).\n\n"
        "Puedes usar emojis y HTML básico: "
        "&lt;b&gt;negrita&lt;/b&gt;, &lt;i&gt;cursiva&lt;/i&gt;.\n"
        "Antes de enviarlo verás una vista previa y tendrás que confirmarlo.\n\n"
        "❌ /cancelar para cancelar.",
        parse_mode="HTML"
    )


async def admin_broadcast_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if not text:
        return

    if len(text) > BROADCAST_MAX_CHARS:
        await update.message.reply_text(
            f"⚠️ El mensaje es demasiado largo ({len(text)} caracteres). "
            f"El máximo es {BROADCAST_MAX_CHARS}. Acórtalo y envíalo de nuevo, "
            "o usa /cancelar."
        )
        return

    parse_mode = "HTML"
    note = ""

    try:
        await update.message.reply_text(
            BROADCAST_HEADER_HTML + text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=broadcast_keyboard()
        )
    except Exception as error:
        logger.warning("Vista previa del aviso: HTML rechazado (%s)", error)
        parse_mode = None
        note = "\n\n⚠️ El HTML no era válido: se enviará como texto plano."
        await update.message.reply_text(
            BROADCAST_HEADER_PLAIN + text,
            disable_web_page_preview=True,
            reply_markup=broadcast_keyboard()
        )

    context.user_data["broadcast_draft"] = {
        "text": text,
        "parse_mode": parse_mode
    }
    context.user_data.pop("admin_action", None)

    total = len(broadcast_recipient_ids())

    await update.message.reply_text(
        f"👆 Así lo verán los usuarios.\n\n"
        f"¿Enviarlo ahora a <b>{total}</b> usuarios?{note}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Enviar ahora", callback_data="admin_broadcast_send")],
            [InlineKeyboardButton("✏️ Reescribir", callback_data="admin_broadcast")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="admin_broadcast_cancel")]
        ])
    )


async def _run_broadcast(bot, admin_chat_id, draft, recipients):
    sent = 0
    blocked = 0
    failed = 0

    parse_mode = draft.get("parse_mode")
    body = (
        (BROADCAST_HEADER_HTML if parse_mode else BROADCAST_HEADER_PLAIN)
        + draft["text"]
    )

    for user_id in recipients:
        for attempt in range(2):
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=body,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                    reply_markup=broadcast_keyboard()
                )
                sent += 1
                break
            except RetryAfter as error:
                await asyncio.sleep(float(getattr(error, "retry_after", 5)) + 1)
                if attempt == 1:
                    failed += 1
            except Forbidden:
                blocked += 1
                break
            except Exception as error:
                logger.warning("Aviso no enviado a %s: %s", user_id, error)
                failed += 1
                break

        # Telegram permite unos 30 mensajes por segundo; se envía más despacio.
        await asyncio.sleep(0.06)

    logger.info(
        "Aviso a usuarios terminado: enviados=%s, bloqueados=%s, fallidos=%s",
        sent, blocked, failed
    )

    try:
        await bot.send_message(
            chat_id=admin_chat_id,
            text=(
                "✅ <b>Envío terminado</b>\n\n"
                f"📨 Entregados: <b>{sent}</b>\n"
                f"🚫 Han bloqueado el bot: <b>{blocked}</b>\n"
                f"⚠️ Fallidos: <b>{failed}</b>"
            ),
            parse_mode="HTML",
            reply_markup=admin_menu_keyboard()
        )
    except Exception as error:
        logger.error("No se pudo enviar el informe del aviso al admin: %s", error)


async def admin_broadcast_send(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return

    draft = context.user_data.pop("broadcast_draft", None)

    if not draft:
        await query.edit_message_text(
            "⚠️ No hay ningún mensaje pendiente de enviar.",
            reply_markup=admin_menu_keyboard()
        )
        return

    recipients = broadcast_recipient_ids()

    if not recipients:
        await query.edit_message_text(
            "⚠️ Todavía no hay usuarios registrados a quienes enviar el mensaje.",
            reply_markup=admin_menu_keyboard()
        )
        return

    await query.edit_message_text(
        f"📤 Enviando el mensaje a {len(recipients)} usuarios...\n\n"
        "Te avisaré aquí cuando termine. Mientras tanto el bot sigue funcionando con normalidad."
    )

    task = asyncio.create_task(
        _run_broadcast(context.bot, query.from_user.id, draft, recipients)
    )
    _BROADCAST_TASKS.add(task)
    task.add_done_callback(_BROADCAST_TASKS.discard)


async def admin_broadcast_cancel(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return

    context.user_data.pop("broadcast_draft", None)
    context.user_data.pop("admin_action", None)

    await query.edit_message_text(
        "❌ Envío cancelado. No se ha enviado nada.",
        reply_markup=admin_menu_keyboard()
    )


# ============================================================
# ALERTAS DE ALTO IMPACTO CON EXPLICACIÓN Y ESCENARIOS
# ============================================================

HIGH_IMPACT_BEFORE_MINUTES = 30
HIGH_IMPACT_RESULT_WINDOW_MINUTES = 240

# (par, sube_cuando_la_divisa_se_fortalece)
EVENT_PAIR_MOVES = {
    "USD": [("EUR/USD", False), ("GBP/USD", False), ("USD/JPY", True), ("AUD/USD", False)],
    "EUR": [("EUR/USD", True), ("EUR/GBP", True), ("EUR/JPY", True)],
    "GBP": [("GBP/USD", True), ("GBP/JPY", True), ("EUR/GBP", False)],
    "JPY": [("USD/JPY", False), ("GBP/JPY", False), ("EUR/JPY", False)],
    "CAD": [("USD/CAD", False), ("CAD/JPY", True)],
    "AUD": [("AUD/USD", True), ("AUD/JPY", True)],
    "NZD": [("NZD/USD", True), ("NZD/JPY", True)],
    "CHF": [("USD/CHF", False), ("EUR/CHF", False)]
}

CENTRAL_BANK_PHRASES = (
    "federal reserve", "rate decision", "interest rate", "monetary policy",
    "policy rate", "bank of england", "bank of japan", "bank of canada",
    "riksbank", "norges"
)
CENTRAL_BANK_ACRONYMS = re.compile(
    r"\b(?:fomc|ecb|boe|boj|boc|rba|rbnz|snb|pboc)\b"
)

INVERSE_WORDS = ("unemployment", "jobless", "claims")


def event_kind(name):
    text = str(name or "").lower()

    if any(phrase in text for phrase in CENTRAL_BANK_PHRASES) or CENTRAL_BANK_ACRONYMS.search(text):
        return "central_bank"

    if any(word in text for word in INVERSE_WORDS):
        return "inverse"

    return "normal"


def parse_event_number(value):
    """Convierte textos como '3.0% y/y' o '225K' en un número comparable."""

    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([KkMmBbTt])?(?![A-Za-z])", text)

    if not match:
        return None

    number = float(match.group(1))
    multiplier = {
        "k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12
    }.get((match.group(2) or "").lower(), 1)

    return number * multiplier


def _pair_moves_text(currency, strong):
    parts = []

    for pair, up_when_strong in EVENT_PAIR_MOVES.get(currency, []):
        goes_up = up_when_strong if strong else not up_when_strong
        parts.append(f"{pair} {'↑' if goes_up else '↓'}")

    return " · ".join(parts)


def _other_assets_text(currency, strong):
    if currency == "USD":
        arrow = "↓" if strong else "↑"
        return (
            f"XAU/USD {arrow} · BTC/USD {arrow} (suelen moverse en sentido "
            "inverso al dólar, aunque no siempre) · US30: reacción mixta, "
            "depende de si el mercado lo lee como crecimiento o como tipos más altos"
        )

    if currency in EVENT_PAIR_MOVES:
        return (
            "XAU/USD, US30 y BTC/USD: efecto indirecto, a través del dólar "
            "y del apetito por riesgo"
        )

    return ""


def event_scenarios_html(name, currency):
    cur = str(currency or "").upper()
    kind = event_kind(name)

    if kind == "central_bank":
        up_label = "🦅 Más restrictivo (hawkish) que el consenso"
        down_label = "🕊️ Más flexible (dovish) que el consenso"
    elif kind == "inverse":
        up_label = "📈 Dato mejor que el consenso (menos desempleo o peticiones)"
        down_label = "📉 Dato peor que el consenso (más desempleo o peticiones)"
    else:
        up_label = "📈 Dato superior al consenso"
        down_label = "📉 Dato inferior al consenso"

    lines = []

    if cur in EVENT_PAIR_MOVES:
        for strong, label in ((True, up_label), (False, down_label)):
            verb = "fortalecerse" if strong else "debilitarse"
            lines.append(f"<b>{label}</b>")
            lines.append(
                f"→ {escape(cur)} tiende a {verb}: {_pair_moves_text(cur, strong)}"
            )
            others = _other_assets_text(cur, strong)
            if others:
                lines.append(f"→ {escape(others)}")
            lines.append("")
    else:
        lines.append(
            "El efecto sobre pares y activos depende de la divisa afectada; "
            "compara el resultado con el consenso."
        )
        lines.append("")

    lines.append("↔️ <b>Dato en línea con el consenso</b>")
    lines.append(
        "→ La reacción suele ser limitada; el mercado se fija en el detalle y el tono."
    )

    if kind == "central_bank":
        lines.append("")
        lines.append(
            "ℹ️ En bancos centrales importa tanto la decisión como el comunicado "
            "y la rueda de prensa: la primera reacción puede revertirse."
        )

    return "\n".join(lines)


def _alert_time_line(moment):
    local = moment.astimezone(CALENDAR_TZ)

    if CALENDAR_TZ_LABEL == "UTC":
        return f"🕒 {moment:%H:%M} UTC"

    return f"🕒 {moment:%H:%M} UTC · {local:%H:%M} ({escape(CALENDAR_TZ_LABEL)})"


ALERT_DISCLAIMER = (
    "⚠️ <b>Aviso y riesgo:</b> contenido informativo y educativo. No es una señal ni "
    "una recomendación de entrada; los escenarios son tendencias habituales y no "
    "una predicción. Las noticias pueden provocar picos de volatilidad, spreads más "
    "amplios y deslizamiento: gestiona tu riesgo y evita sobreexponerte durante la "
    "publicación.\n\n"
    '📊 Datos: <a href="https://www.financecalendar.com">FinanceCalendar.com</a>'
)


def build_high_impact_alert(event, minutes):
    name = str(event_value(event, "name", "title", "event") or "Evento económico")
    currency = event_currency(event).upper()
    moment = event_datetime_utc(event)
    profile = calendar_event_profile(name)

    if minutes > 1:
        when = f"en ~{int(round(minutes))} min"
    else:
        when = "publicándose ahora"

    medium = str(event_value(event, "impact", "importance")).lower() == "medium"
    icon = "🟠" if medium else "🔴"
    header = (
        "🟠 <b>EVENTO ECONÓMICO DE IMPACTO MEDIO</b>"
        if medium else "🚨 <b>EVENTO ECONÓMICO DE ALTO IMPACTO</b>"
    )

    lines = [
        header,
        "",
        f"{icon} <b>{escape(currency or 'N/D')}</b> · {escape(name)}",
        f"{_alert_time_line(moment)} — {when}"
    ]

    consensus = event_value(event, "consensus", "forecast", "expected")
    prior = event_value(event, "prior", "previous")

    refs = []
    if consensus:
        refs.append(f"📊 Consenso: <b>{escape(str(consensus))}</b>")
    if prior:
        refs.append(f"⏮️ Anterior: <b>{escape(str(prior))}</b>")
    if refs:
        lines.append(" · ".join(refs))

    lines.extend([
        "",
        "📖 <b>¿Qué es?</b>",
        escape(profile["measure"]),
        "",
        "🏦 <b>¿Por qué importa?</b>",
        escape(profile["why"]),
        "",
        "🎯 <b>Escenarios según el resultado frente al consenso</b>",
        "",
        event_scenarios_html(name, currency),
        ""
    ])

    if medium:
        lines.extend([
            "ℹ️ <b>Impacto medio:</b> la reacción suele ser menor que en un evento rojo, "
            "pero un dato muy alejado del consenso puede mover con fuerza los pares de "
            f"{escape(currency or 'la divisa')}.",
            ""
        ])

    lines.append(ALERT_DISCLAIMER)

    return "\n".join(lines)[:4000]


def build_result_alert(event):
    name = str(event_value(event, "name", "title", "event") or "Evento económico")
    currency = event_currency(event).upper()
    consensus = event_value(event, "consensus", "forecast", "expected")
    prior = event_value(event, "prior", "previous")
    actual = event_value(event, "actual")
    kind = event_kind(name)

    consensus_number = parse_event_number(consensus)
    actual_number = parse_event_number(actual)

    reading = (
        "Compara el dato publicado con el consenso: la reacción depende de "
        "cuánto se aleja de lo esperado."
    )

    if consensus_number is not None and actual_number is not None:
        diff = actual_number - consensus_number

        if abs(diff) < 1e-9:
            reading = (
                "↔️ <b>En línea con el consenso.</b> La reacción suele ser limitada; "
                "el mercado mira el detalle del informe."
            )
        else:
            above = diff > 0
            strong = (not above) if kind == "inverse" else above

            if kind == "central_bank":
                what = "más restrictivo" if above else "más flexible"
                head = f"{'🦅' if above else '🕊️'} <b>Resultado {what} que el consenso.</b>"
            else:
                what = "superior" if above else "inferior"
                extra = ""
                if kind == "inverse":
                    extra = f" ({'más' if above else 'menos'} desempleo/peticiones)"
                head = f"{'📈' if above else '📉'} <b>Dato {what} al consenso{extra}.</b>"

            if currency in EVENT_PAIR_MOVES:
                verb = "fortalecerse" if strong else "debilitarse"
                reading = (
                    f"{head}\n→ {escape(currency)} tendería a {verb}: "
                    f"{_pair_moves_text(currency, strong)}\n"
                    f"→ {escape(_other_assets_text(currency, strong))}"
                )
            else:
                reading = head

    medium = str(event_value(event, "impact", "importance")).lower() == "medium"

    lines = [
        "✅ <b>RESULTADO PUBLICADO — " + ("IMPACTO MEDIO" if medium else "ALTO IMPACTO") + "</b>",
        "",
        f"{'🟠' if medium else '🔴'} <b>{escape(currency or 'N/D')}</b> · {escape(name)}",
        f"✅ Actual: <b>{escape(str(actual))}</b>"
    ]

    refs = []
    if consensus:
        refs.append(f"📊 Consenso: <b>{escape(str(consensus))}</b>")
    if prior:
        refs.append(f"⏮️ Anterior: <b>{escape(str(prior))}</b>")
    if refs:
        lines.append(" · ".join(refs))

    lines.extend([
        "",
        reading,
        "",
        "ℹ️ La primera reacción del mercado puede ser brusca y revertirse en minutos.",
        "",
        ALERT_DISCLAIMER
    ])

    return "\n".join(lines)[:4000]


def _env_flag(name, default=True):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _env_num(name, default, cast=float):
    try:
        return cast(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


COMMUNITY_IMPACT_LEVELS = ("high", "medium")
MEDIUM_IMPACT_ENABLED = _env_flag("MEDIUM_IMPACT_ENABLED", True)
MEDIUM_IMPACT_MAX_PER_DAY = _env_num("MEDIUM_IMPACT_MAX_PER_DAY", 10, int)


def _medium_sent_today(seen):
    prefix = "medium|" + datetime.utcnow().strftime("%Y-%m-%d")
    return sum(1 for value in seen.values() if str(value).startswith(prefix))


async def community_high_impact_monitor(application):
    while True:
        try:
            channel_id = get_community_channel_id()

            if channel_id:
                today = today_date()
                events = []

                for level in COMMUNITY_IMPACT_LEVELS:
                    if level == "medium" and not MEDIUM_IMPACT_ENABLED:
                        continue

                    batch = await fetch_calendar_events(
                        today - timedelta(days=1),
                        today + timedelta(days=1),
                        impact=level
                    )
                    events.extend(batch or [])

                seen = _load_json_file(COMMUNITY_EVENTS_FILE, {})
                now = datetime.now(timezone.utc)
                changed = False
                handled = set()

                for event in events:
                    level = str(event_value(event, "impact", "importance")).lower()

                    if level not in COMMUNITY_IMPACT_LEVELS:
                        continue

                    if level == "medium" and not MEDIUM_IMPACT_ENABLED:
                        continue

                    moment = event_datetime_utc(event)

                    if not moment:
                        continue

                    name = str(event_value(event, "name", "title", "event") or "Evento económico")
                    currency = event_currency(event).upper() or "N/D"
                    minutes = (moment - now).total_seconds() / 60
                    base_key = str(
                        event_value(event, "id", "event_id")
                        or f"{name}|{currency}|{moment.isoformat()}"
                    )

                    if base_key in handled:
                        continue

                    handled.add(base_key)
                    medium = level == "medium"

                    # El impacto medio sólo se publica para las divisas principales,
                    # para no llenar el Canal con indicadores de divisas secundarias.
                    if medium and currency not in EVENT_PAIR_MOVES:
                        continue

                    stamp = (
                        ("medium|" if medium else "")
                        + datetime.utcnow().isoformat() + "Z"
                    )

                    # 1) Aviso previo con explicación y escenarios.
                    if (
                        -5 <= minutes <= HIGH_IMPACT_BEFORE_MINUTES
                        and base_key not in seen
                        and (not medium or _medium_sent_today(seen) < MEDIUM_IMPACT_MAX_PER_DAY)
                    ):
                        try:
                            await application.bot.send_message(
                                chat_id=channel_id,
                                text=build_high_impact_alert(event, minutes),
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                            seen[base_key] = stamp
                            changed = True
                        except Exception as error:
                            logger.error("No se pudo publicar el aviso de %s: %s", name, error)

                    # 2) Resultado publicado frente al consenso.
                    # En impacto medio sólo se publica si antes se avisó del evento.
                    result_key = base_key + "|result"

                    if (
                        event_value(event, "actual")
                        and -HIGH_IMPACT_RESULT_WINDOW_MINUTES <= minutes <= 0
                        and result_key not in seen
                        and (not medium or base_key in seen)
                    ):
                        try:
                            await application.bot.send_message(
                                chat_id=channel_id,
                                text=build_result_alert(event),
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                            seen[result_key] = datetime.utcnow().isoformat() + "Z"
                            changed = True
                        except Exception as error:
                            logger.error("No se pudo publicar el resultado de %s: %s", name, error)

                if changed:
                    for old_key in list(seen)[:-500]:
                        seen.pop(old_key, None)
                    _save_json_file(COMMUNITY_EVENTS_FILE, seen)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("Error en monitor de eventos (alto/medio impacto): %s", error, exc_info=True)

        await asyncio.sleep(HIGH_IMPACT_CHECK_SECONDS)


# ============================================================
# ALERTAS TÉCNICAS APEXQUANT (SMART MONEY) — MOTOR DE ANÁLISIS
# ============================================================
# Metodología (H4 → H1 → M5):
#   H4  : dirección/tendencia (estructura HH/HL o LH/LL + EMA 50).
#   H1  : zonas de liquidez (máximos/mínimos, equal highs/lows), imbalances (FVG)
#         y order blocks (OB); además rangos laterales y canales.
#   M5  : entrada/POI. Barrido de liquidez dentro de una zona H1, cierre de vela a
#         favor (recuperación del nivel) y vela de confirmación a favor de H4.
#   S/R : en rangos o canales, ruptura → cierre de vela (ruptura real o barrido)
#         → vela de continuación.
# Son ALERTAS informativas: no son señales ni recomendaciones de entrada.

TWELVEDATA_API_KEY = _clean_key(os.getenv("TWELVEDATA_API_KEY"))
TWELVEDATA_TS_URL = "https://api.twelvedata.com/time_series"
TECH_ALERTS_FILE = os.getenv("TECH_ALERTS_FILE", "/data/tech_alerts.json").strip()

TECH_ALERTS_AUTOSTART = _env_flag("TECH_ALERTS_ENABLED", True)
TECH_TICK_SECONDS = 60
TECH_M5_NEAR_SECONDS = _env_num("TECH_M5_NEAR_SECONDS", 300, int)    # precio cerca de una zona
TECH_M5_FAR_SECONDS = _env_num("TECH_M5_FAR_SECONDS", 900, int)      # precio lejos de las zonas
TECH_H1_TTL_SECONDS = _env_num("TECH_H1_TTL_SECONDS", 3600, int)
TECH_H4_TTL_SECONDS = _env_num("TECH_H4_TTL_SECONDS", 7200, int)
TD_DAILY_BUDGET = _env_num("TWELVEDATA_DAILY_BUDGET", 740, int)      # plan gratis: 800/día
TD_PER_MINUTE = _env_num("TWELVEDATA_PER_MINUTE", 7, int)            # plan gratis: 8/min

TECH_MIN_SCORE = _env_num("TECH_MIN_SCORE", 2, int)                  # confluencias extra mínimas
TECH_COOLDOWN_MINUTES = _env_num("TECH_COOLDOWN_MINUTES", 45, int)
TECH_MAX_PER_SYMBOL_DAY = _env_num("TECH_MAX_PER_SYMBOL_DAY", 3, int)
TECH_MAX_PER_DAY = _env_num("TECH_MAX_PER_DAY", 10, int)
TECH_ACTIVE_START_UTC = _env_num("TECH_ACTIVE_START_UTC", 6, int)    # Londres
TECH_ACTIVE_END_UTC = _env_num("TECH_ACTIVE_END_UTC", 21, int)       # cierre de Nueva York
TECH_SWEEP_LOOKBACK = 18        # velas M5 (~90 min) en las que se busca el barrido
TECH_NEWS_AHEAD_MINUTES = _env_num("TECH_NEWS_AHEAD_MINUTES", 240, int)
TECH_NEWS_BEHIND_MINUTES = _env_num("TECH_NEWS_BEHIND_MINUTES", 60, int)
TECH_NEWS_DANGER_MINUTES = 30   # noticia roja a menos de este margen = riesgo elevado

TECH_SYMBOLS = {
    "GBP/USD": {
        "td": "GBP/USD", "tv": "OANDA:GBPUSD", "digits": 5, "ccy": ("GBP", "USD"),
        "kind": "fx", "emoji": "💷",
        "risk": "Es sensible a datos de Reino Unido y de EE. UU. y puede moverse con fuerza en la apertura de Londres y Nueva York."
    },
    "GBP/JPY": {
        "td": "GBP/JPY", "tv": "OANDA:GBPJPY", "digits": 3, "ccy": ("GBP", "JPY"),
        "kind": "fx", "emoji": "💴",
        "risk": "Es un cruce muy volátil: los movimientos son rápidos y el spread puede ampliarse en noticias."
    },
    "US30": {
        "td": os.getenv("TECH_SYMBOL_US30", "DJI").strip() or "DJI",
        # Alternativas gratuitas si el índice no está en el plan: ETF DIA (≈ Dow / 100)
        "td_alts": [(os.getenv("TECH_SYMBOL_US30_ALT", "DIA").strip() or "DIA",
                     _env_num("TECH_US30_ALT_SCALE", 100.0, float))],
        "tv": "OANDA:US30USD", "digits": 1, "ccy": ("USD",),
        "kind": "index", "emoji": "🏛️",
        "risk": "Es un índice: puede abrir con gaps y reaccionar con fuerza a datos de EE. UU. y resultados de empresas."
    },
    "BTC/USD": {
        "td": "BTC/USD", "tv": "BITSTAMP:BTCUSD", "digits": 1, "ccy": ("USD",),
        "kind": "crypto", "emoji": "₿",
        "risk": "Es un activo de volatilidad muy alta que cotiza 24/7; la liquidez puede ser baja en fines de semana y horas nocturnas."
    },
    "XAU/USD": {
        "td": "XAU/USD", "tv": "OANDA:XAUUSD", "digits": 2, "ccy": ("USD",),
        "kind": "metal", "emoji": "🥇",
        "risk": "El oro reacciona con fuerza a datos de EE. UU., a la Fed y a movimientos del dólar; el spread puede ampliarse."
    }
}

TECH_RISK_BASE = (
    "⚠️ <b>Gestión del riesgo:</b> alerta informativa y educativa; no es una señal "
    "ni una recomendación de entrada. Un barrido o una vela de confirmación no "
    "garantizan continuidad y el escenario puede fallar. Define antes tu riesgo por "
    "operación (un porcentaje bajo y fijo de tu capital), usa siempre stop loss y "
    "ten en cuenta spread, deslizamiento y noticias."
)

TECH_STATE = {}
TECH_RUNTIME = {}
_TECH_TASKS = set()
_TD_CALLS = []
_TD_LOCK = None


class TechDataError(Exception):
    pass


class TechRateLimit(TechDataError):
    pass


class TechBudgetError(TechDataError):
    pass


class TechSymbolError(TechDataError):
    pass


# ------------------------------------------------------------
# Estado persistente
# ------------------------------------------------------------

def _tech_today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def tech_state_load():
    global TECH_STATE
    data = _load_json_file(TECH_ALERTS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("enabled", TECH_ALERTS_AUTOSTART)
    data.setdefault("budget", {"day": _tech_today(), "used": 0})
    data.setdefault("sent", {})
    data.setdefault("daily", {"day": _tech_today(), "total": 0, "by_symbol": {}})
    data.setdefault("last_alert", {})
    data.setdefault("history", [])
    data["disabled"] = {}  # al reiniciar/desplegar se reintentan los activos pausados por error de símbolo
    data.setdefault("notified", {})
    data.setdefault("td_sym", {})   # símbolo de Twelve Data que funciona por activo
    data.setdefault("td_bad", {})   # símbolos que fallaron (pausa temporal)
    TECH_STATE = data
    return data


def tech_state_save():
    try:
        sent = TECH_STATE.get("sent", {})
        if len(sent) > 300:
            for old_key in list(sent)[:-300]:
                sent.pop(old_key, None)
        TECH_STATE["history"] = TECH_STATE.get("history", [])[-20:]
        _save_json_file(TECH_ALERTS_FILE, TECH_STATE)
    except Exception as error:
        logger.error("No se pudo guardar el estado de alertas técnicas: %s", error)


def _tech_roll_day():
    today = _tech_today()
    if TECH_STATE.get("budget", {}).get("day") != today:
        TECH_STATE["budget"] = {"day": today, "used": 0}
    if TECH_STATE.get("daily", {}).get("day") != today:
        TECH_STATE["daily"] = {"day": today, "total": 0, "by_symbol": {}}
    TECH_STATE["notified"] = {
        k: v for k, v in TECH_STATE.get("notified", {}).items() if str(k).endswith(today)
    }


def tech_budget_used():
    _tech_roll_day()
    return int(TECH_STATE["budget"].get("used", 0))


# ------------------------------------------------------------
# Twelve Data (con control de créditos)
# ------------------------------------------------------------

def _td_fetch_blocking(symbol, interval, outputsize):
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "order": "asc",
        "timezone": "UTC",
        "apikey": TWELVEDATA_API_KEY
    }
    request = Request(
        TWELVEDATA_TS_URL + "?" + urlencode(params),
        headers={"User-Agent": "Mozilla/5.0 ApexQuantBot/1.0", "Accept": "application/json"}
    )

    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8"))
        except Exception:
            return {"status": "error", "code": error.code, "message": f"HTTP {error.code}"}


def tech_parse_candles(data):
    values = data.get("values") if isinstance(data, dict) else None
    candles = []

    for row in values or []:
        try:
            raw = str(row.get("datetime"))
            fmt = "%Y-%m-%d %H:%M:%S" if " " in raw else "%Y-%m-%d"
            moment = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            candle = {
                "t": moment,
                "o": float(row["open"]),
                "h": float(row["high"]),
                "l": float(row["low"]),
                "c": float(row["close"]),
                "v": float(row.get("volume") or 0)
            }
        except (KeyError, TypeError, ValueError):
            continue

        if candle["h"] < candle["l"]:
            continue

        candles.append(candle)

    candles.sort(key=lambda c: c["t"])
    return candles


def tech_closed_candles(candles, interval_seconds, now=None):
    """Descarta la vela en formación: sólo se analizan velas ya cerradas."""
    now = now or datetime.now(timezone.utc)
    return [c for c in candles if c["t"].timestamp() + interval_seconds <= now.timestamp()]


async def td_get_candles(symbol, interval, outputsize):
    global _TD_LOCK

    if not TWELVEDATA_API_KEY:
        raise TechDataError("falta TWELVEDATA_API_KEY")

    _tech_roll_day()

    if TECH_STATE["budget"]["used"] >= TD_DAILY_BUDGET:
        raise TechBudgetError("presupuesto diario de Twelve Data agotado")

    if _TD_LOCK is None:
        _TD_LOCK = asyncio.Lock()

    async with _TD_LOCK:
        while True:
            now = time.monotonic()
            while _TD_CALLS and now - _TD_CALLS[0] >= 61:
                _TD_CALLS.pop(0)
            if len(_TD_CALLS) < TD_PER_MINUTE:
                break
            await asyncio.sleep(max(0.5, 61 - (now - _TD_CALLS[0])))

        _TD_CALLS.append(time.monotonic())
        TECH_STATE["budget"]["used"] = int(TECH_STATE["budget"].get("used", 0)) + 1

    loop = asyncio.get_running_loop()

    try:
        data = await loop.run_in_executor(None, _td_fetch_blocking, symbol, interval, outputsize)
    except Exception as error:
        raise TechDataError(f"sin conexión con Twelve Data ({error})")

    if isinstance(data, dict) and data.get("status") == "error":
        code = int(data.get("code") or 0)
        message = str(data.get("message") or "error")[:160]

        if code == 429:
            raise TechRateLimit(message)
        if code in (401, 403) and "plan" not in message.lower() and "symbol" not in message.lower():
            raise TechDataError(f"clave rechazada: {message}")
        if code in (400, 403, 404):
            raise TechSymbolError(message)
        raise TechDataError(message)

    candles = tech_parse_candles(data)

    if not candles:
        raise TechDataError(f"{symbol} {interval}: respuesta sin velas")

    return candles


# ------------------------------------------------------------
# Indicadores y estructura
# ------------------------------------------------------------

def tech_atr(candles, period=14):
    if len(candles) < period + 1:
        return None

    total = 0.0

    for i in range(len(candles) - period, len(candles)):
        prev_close = candles[i - 1]["c"]
        total += max(
            candles[i]["h"] - candles[i]["l"],
            abs(candles[i]["h"] - prev_close),
            abs(candles[i]["l"] - prev_close)
        )

    value = total / period
    return value if value > 0 else None


def tech_ema(values, period):
    if not values:
        return None

    period = min(period, len(values))
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period

    for value in values[period:]:
        ema = value * k + ema * (1 - k)

    return ema


def tech_find_swings(candles, left=2, right=2):
    highs, lows = [], []

    for i in range(left, len(candles) - right):
        hi, lo = candles[i]["h"], candles[i]["l"]

        if (
            all(hi > candles[j]["h"] for j in range(i - left, i))
            and all(hi >= candles[j]["h"] for j in range(i + 1, i + right + 1))
        ):
            highs.append((i, hi))

        if (
            all(lo < candles[j]["l"] for j in range(i - left, i))
            and all(lo <= candles[j]["l"] for j in range(i + 1, i + right + 1))
        ):
            lows.append((i, lo))

    return highs, lows


def tech_h4_bias(c4):
    """Dirección H4: estructura de máximos/mínimos + EMA 50."""

    neutral = {"dir": "neutral", "label": "Neutral / rango", "range": None}

    if len(c4) < 30:
        neutral["reason"] = "datos H4 insuficientes"
        return neutral

    a = tech_atr(c4)

    if not a:
        neutral["reason"] = "sin volatilidad medible"
        return neutral

    highs, lows = tech_find_swings(c4, 2, 2)

    if len(highs) < 2 or len(lows) < 2:
        neutral["reason"] = "estructura H4 sin definir"
        return neutral

    (hi_idx, last_h), (_, prev_h) = highs[-1], highs[-2]
    (lo_idx, last_l), (_, prev_l) = lows[-1], lows[-2]
    tol = 0.2 * a
    close = c4[-1]["c"]
    ema = tech_ema([c["c"] for c in c4], 50)

    hh, lh = last_h > prev_h + tol, last_h < prev_h - tol
    hl, ll = last_l > prev_l + tol, last_l < prev_l - tol

    if hh and hl:
        if close <= last_l:
            neutral["reason"] = "estructura alcista rota (cierre bajo el último mínimo)"
            return neutral
        if ema is not None and close < ema - 0.5 * a:
            neutral["reason"] = "estructura alcista pero precio bajo la EMA 50"
            return neutral

        top = max(c["h"] for c in c4[lo_idx:])
        return {
            "dir": "bull", "label": "Alcista (HH/HL)",
            "range": (last_l, top), "ema": ema, "reason": ""
        }

    if lh and ll:
        if close >= last_h:
            neutral["reason"] = "estructura bajista rota (cierre sobre el último máximo)"
            return neutral
        if ema is not None and close > ema + 0.5 * a:
            neutral["reason"] = "estructura bajista pero precio sobre la EMA 50"
            return neutral

        bottom = min(c["l"] for c in c4[hi_idx:])
        return {
            "dir": "bear", "label": "Bajista (LH/LL)",
            "range": (bottom, last_h), "ema": ema, "reason": ""
        }

    neutral["reason"] = "estructura mixta (rango o transición)"
    return neutral


def tech_zone_overlap(a, b, tol=0.0):
    return a["low"] <= b["high"] + tol and a["high"] >= b["low"] - tol


def tech_h1_zones(c1, max_age=150):
    """Zonas H1: FVG (imbalance), OB y piscinas de liquidez sin barrer."""

    c1 = c1[-max_age:]
    a = tech_atr(c1)

    if not a or len(c1) < 20:
        return [], None

    n = len(c1)
    zones = []

    # Imbalances (FVG) no rellenados por completo.
    for i in range(2, n):
        first, third = c1[i - 2], c1[i]

        gap_up = third["l"] - first["h"]
        if gap_up >= 0.15 * a:
            zone = {"kind": "FVG", "side": "demand", "low": first["h"], "high": third["l"],
                    "i": i, "t": c1[i - 1]["t"]}
            if not any(c1[j]["c"] < zone["low"] for j in range(i + 1, n)):
                zones.append(zone)

        gap_down = first["l"] - third["h"]
        if gap_down >= 0.15 * a:
            zone = {"kind": "FVG", "side": "supply", "low": third["h"], "high": first["l"],
                    "i": i, "t": c1[i - 1]["t"]}
            if not any(c1[j]["c"] > zone["high"] for j in range(i + 1, n)):
                zones.append(zone)

    # Order blocks: última vela contraria antes de un desplazamiento que rompe estructura.
    for i in range(1, n - 1):
        base, impulse = c1[i], c1[i + 1]
        body = abs(impulse["c"] - impulse["o"])

        if body < 1.2 * a:
            continue

        window = c1[max(0, i - 5):i]
        if not window:
            continue

        if base["c"] < base["o"] and impulse["c"] > impulse["o"] and impulse["c"] > base["h"] \
                and impulse["c"] > max(c["h"] for c in window):
            zone = {"kind": "OB", "side": "demand", "low": base["l"], "high": base["h"],
                    "i": i, "t": base["t"]}
            if not any(c1[j]["c"] < zone["low"] for j in range(i + 2, n)):
                zones.append(zone)

        if base["c"] > base["o"] and impulse["c"] < impulse["o"] and impulse["c"] < base["l"] \
                and impulse["c"] < min(c["l"] for c in window):
            zone = {"kind": "OB", "side": "supply", "low": base["l"], "high": base["h"],
                    "i": i, "t": base["t"]}
            if not any(c1[j]["c"] > zone["high"] for j in range(i + 2, n)):
                zones.append(zone)

    # Liquidez: máximos/mínimos H1 que todavía no han sido barridos.
    highs, lows = tech_find_swings(c1, 3, 3)

    for idx, price in lows[-8:]:
        if min(c["l"] for c in c1[idx + 1:]) < price:
            continue
        equal = sum(1 for _, q in lows if abs(q - price) <= 0.15 * a) >= 2
        zones.append({"kind": "LIQ", "side": "demand", "low": price - 0.5 * a,
                      "high": price + 0.25 * a, "level": price, "equal": equal,
                      "i": idx, "t": c1[idx]["t"]})

    for idx, price in highs[-8:]:
        if max(c["h"] for c in c1[idx + 1:]) > price:
            continue
        equal = sum(1 for _, q in highs if abs(q - price) <= 0.15 * a) >= 2
        zones.append({"kind": "LIQ", "side": "supply", "low": price - 0.25 * a,
                      "high": price + 0.5 * a, "level": price, "equal": equal,
                      "i": idx, "t": c1[idx]["t"]})

    # Confluencia: FVG/OB solapado con liquidez (o entre sí).
    for zone in zones:
        zone["conf"] = any(
            other is not zone and other["side"] == zone["side"]
            and other["kind"] != zone["kind"]
            and tech_zone_overlap(zone, other, 0.1 * a)
            for other in zones
        )

    last_price = c1[-1]["c"]
    zones = [z for z in zones if abs((z["low"] + z["high"]) / 2 - last_price) <= 8 * a]
    zones.sort(key=lambda z: abs((z["low"] + z["high"]) / 2 - last_price))

    return zones[:16], a


def tech_next_liquidity(c1, price, direction):
    """Máximo (arriba) o mínimo (abajo) H1 sin barrer más cercano, como referencia."""

    c1 = c1[-150:]
    highs, lows = tech_find_swings(c1, 3, 3)
    best = None

    if direction == "up":
        for idx, p in highs:
            if p > price and not max([c["h"] for c in c1[idx + 1:]] or [0]) > p:
                if best is None or p < best:
                    best = p
    else:
        for idx, p in lows:
            if p < price and not min([c["l"] for c in c1[idx + 1:]] or [p + 1]) < p:
                if best is None or p > best:
                    best = p

    return best


# ------------------------------------------------------------
# Rango lateral / canal en H1
# ------------------------------------------------------------

def _tech_fit_line(points):
    n = len(points)
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    denom = n * sxx - sx * sx

    if abs(denom) < 1e-12:
        return 0.0, sy / n

    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


def tech_line_value(line, moment):
    return line["p0"] + line["s"] * ((moment.timestamp() - line["t0"]) / 3600.0)


def _tech_envelope(points, tol, upper):
    """Mejor recta que actúa como techo (o suelo) de los pivotes, con ≥2 toques."""

    best = None

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            (x1, y1), (x2, y2) = points[i], points[j]

            if x2 - x1 < 3:
                continue

            slope = (y2 - y1) / (x2 - x1)
            intercept = y1 - slope * x1

            def gap(point):
                x, y = point
                line = slope * x + intercept
                return (y - line) if upper else (line - y)

            if any(gap(point) > tol for point in points):
                continue

            touches = [point for point in points if abs(gap(point)) <= tol]

            if len(touches) < 2:
                continue

            score = (len(touches), touches[-1][0] - touches[0][0])

            if best is None or score > best[0]:
                best = (score, touches)

    if best is None:
        return None

    touches = best[1]
    slope, intercept = _tech_fit_line(touches)
    return slope, intercept, len(touches)


def tech_h1_channel(c1):
    look = c1[-60:]
    a = tech_atr(c1)

    if not a or len(look) < 30:
        return None

    highs, lows = tech_find_swings(look, 2, 2)

    if len(highs) < 2 or len(lows) < 2:
        return None

    t0 = look[0]["t"].timestamp()

    def hours_at(moment):
        return (moment.timestamp() - t0) / 3600.0

    pts_h = [(hours_at(look[i]["t"]), p) for i, p in highs[-7:]]
    pts_l = [(hours_at(look[i]["t"]), p) for i, p in lows[-7:]]

    upper = _tech_envelope(pts_h, 0.35 * a, True)
    lower = _tech_envelope(pts_l, 0.35 * a, False)

    if not upper or not lower:
        return None

    s_h, i_h, touches_h = upper
    s_l, i_l, touches_l = lower

    # Líneas aproximadamente paralelas (rango o canal).
    if abs(s_h - s_l) > 0.08 * a:
        return None

    x_end = hours_at(look[-1]["t"])
    upper_now = s_h * x_end + i_h
    lower_now = s_l * x_end + i_l
    width = upper_now - lower_now

    if not (1.2 * a <= width <= 8 * a):
        return None

    # El precio reciente debe seguir dentro de la estructura.
    for candle in look[-6:]:
        x = hours_at(candle["t"])
        up, lo = s_h * x + i_h, s_l * x + i_l
        if not (lo - 0.5 * a <= candle["c"] <= up + 0.5 * a):
            return None

    avg_slope = (s_h + s_l) / 2

    if abs(avg_slope) <= 0.03 * a:
        kind = "Rango lateral"
    elif avg_slope > 0:
        kind = "Canal ascendente"
    else:
        kind = "Canal descendente"

    return {
        "kind": kind,
        "upper": {"t0": t0, "p0": i_h, "s": s_h},
        "lower": {"t0": t0, "p0": i_l, "s": s_l},
        "u_now": upper_now, "l_now": lower_now, "width": width,
        "touches": touches_h + touches_l
    }


# ------------------------------------------------------------
# Marco espejo (los cortos se analizan como largos con precios invertidos)
# ------------------------------------------------------------

def tech_mirror_candles(candles):
    return [
        {"t": c["t"], "o": -c["o"], "h": -c["l"], "l": -c["h"], "c": -c["c"], "v": c["v"]}
        for c in candles
    ]


def tech_mirror_zone(zone):
    mirrored = dict(zone)
    mirrored["low"], mirrored["high"] = -zone["high"], -zone["low"]
    mirrored["side"] = "demand" if zone["side"] == "supply" else "supply"

    if "level" in zone:
        mirrored["level"] = -zone["level"]

    return mirrored


def tech_mirror_line(line):
    return {"t0": line["t0"], "p0": -line["p0"], "s": -line["s"]}


# ------------------------------------------------------------
# M5: barrido de liquidez + cierre a favor + vela de confirmación
# ------------------------------------------------------------

def tech_detect_sweep_long(c5, zones, a1):
    """Marco 'largo': barre mínimos, recupera el nivel y confirma al alza.

    Devuelve el último patrón válido, que debe completarse en las 2 últimas velas.
    """

    n = len(c5)

    if n < 40 or not zones or not a1:
        return None

    a5 = tech_atr(c5)

    if not a5:
        return None

    _, lows = tech_find_swings(c5, 2, 2)
    tol = 0.15 * a1
    vols = [c["v"] for c in c5[-60:] if c["v"] > 0]
    avg_vol = (sum(vols) / len(vols)) if len(vols) >= 20 else 0

    def evaluate(k, level, reclaim):
        sweep = c5[k]
        extreme = min(c["l"] for c in c5[k:reclaim + 1])

        # Vela de confirmación: alcista, con cuerpo, cierra sobre el máximo de la vela de recuperación.
        confirm = None

        for idx in range(reclaim + 1, min(reclaim + 4, n)):
            cand = c5[idx]
            rng = cand["h"] - cand["l"]
            body_ok = rng > 0 and (cand["c"] - cand["o"]) >= 0.4 * rng
            no_new_low = min(c["l"] for c in c5[reclaim + 1:idx + 1]) > extreme

            if cand["c"] > cand["o"] and cand["c"] > c5[reclaim]["h"] and body_ok and no_new_low:
                confirm = idx
                break

        if confirm is None or confirm < n - 2:
            return None

        if any(c["c"] < extreme for c in c5[confirm:]):
            return None

        # El barrido debe ocurrir dentro (o sobre el borde) de una zona H1.
        sweep_range = {"low": extreme, "high": max(c["h"] for c in c5[k:reclaim + 1])}
        hits = [
            z for z in zones
            if tech_zone_overlap(sweep_range, z, tol) and extreme >= z["low"] - 0.75 * a1
        ]

        if not hits:
            return None

        hits.sort(key=lambda z: (not z.get("conf"), z["kind"] == "LIQ"))

        # Estructura menor: cierre de confirmación sobre el último máximo M5 previo al barrido.
        prior_highs = [c["h"] for c in c5[max(0, k - 12):k]]
        choch = bool(prior_highs) and c5[confirm]["c"] > max(prior_highs[-6:])
        vol_ok = avg_vol > 0 and max(c5[k]["v"], c5[confirm]["v"]) > 1.3 * avg_vol

        return {
            "type": "smc", "zone": hits[0], "level": level, "extreme": extreme,
            "confirm_idx": confirm, "confirm_time": c5[confirm]["t"],
            "choch": choch, "vol_ok": vol_ok, "vol_known": avg_vol > 0
        }

    found = None

    for k in range(max(10, n - TECH_SWEEP_LOOKBACK), n - 1):
        sweep = c5[k]

        # Mínimos M5 sin barrer antes de la vela k.
        candidates = [
            p for idx, p in lows
            if k - 60 <= idx <= k - 3 and min(c["l"] for c in c5[idx + 1:k]) >= p
        ]

        for level in sorted(set(candidates), reverse=True):
            if sweep["l"] >= level - 0.02 * a5:
                continue

            # Cierre de vela a favor: la vela de barrido (o la siguiente) recupera el nivel con vela alcista.
            reclaims = []

            if sweep["c"] > level and sweep["c"] > sweep["o"]:
                reclaims.append(k)

            nxt = c5[k + 1]
            if nxt["c"] > level and nxt["c"] > nxt["o"]:
                reclaims.append(k + 1)

            result = None

            for reclaim in reclaims:
                result = evaluate(k, level, reclaim)
                if result:
                    break

            if result:
                found = result
                break

    return found


def tech_detect_smc(c5, zones, bias_dir, a1):
    """Aplica la detección en el sentido de H4 (espejando para cortos)."""

    if bias_dir == "bull":
        result = tech_detect_sweep_long(c5, [z for z in zones if z["side"] == "demand"], a1)
        if result:
            result["dir"] = "bull"
        return result

    if bias_dir == "bear":
        mirrored_zones = [tech_mirror_zone(z) for z in zones if z["side"] == "supply"]
        result = tech_detect_sweep_long(tech_mirror_candles(c5), mirrored_zones, a1)

        if not result:
            return None

        original = {id(m): z for m, z in zip(mirrored_zones, [z for z in zones if z["side"] == "supply"])}
        result["dir"] = "bear"
        result["level"] = -result["level"]
        result["extreme"] = -result["extreme"]
        result["zone"] = original.get(id(result["zone"]), result["zone"])
        return result

    return None


# ------------------------------------------------------------
# M5: ruptura de soporte/resistencia (rango o canal)
# ------------------------------------------------------------

def tech_detect_break_up(c5, line):
    """Marco 'techo': ruptura real alcista o barrido (falsa ruptura) bajista."""

    n = len(c5)

    if n < 40:
        return None

    a5 = tech_atr(c5)

    if not a5:
        return None

    found = None

    for b in range(max(6, n - 10), n - 1):
        brk, nxt = c5[b], c5[b + 1]
        line_b = tech_line_value(line, brk["t"])
        line_n = tech_line_value(line, nxt["t"])

        if brk["h"] <= line_b + 0.02 * a5:
            continue

        # Primera ruptura: las 4 velas previas no superaron la línea.
        if any(c5[j]["h"] > tech_line_value(line, c5[j]["t"]) for j in range(b - 4, b)):
            continue

        if b + 1 < n - 2:
            continue

        closed_above = brk["c"] > line_b + 0.1 * a5
        closed_inside = brk["c"] <= line_b

        if closed_above:
            if (
                nxt["c"] > nxt["o"] and nxt["c"] > brk["c"] and nxt["c"] > line_n
                and nxt["l"] >= line_n - 0.5 * a5
            ):
                found = {"type": "break_real", "dir": "bull", "level": line_n,
                         "extreme": brk["l"], "break_idx": b, "confirm_idx": b + 1,
                         "confirm_time": nxt["t"]}
            elif nxt["c"] < line_n and nxt["c"] < nxt["o"]:
                found = {"type": "break_sweep", "dir": "bear", "level": line_n,
                         "extreme": max(brk["h"], nxt["h"]), "break_idx": b,
                         "confirm_idx": b + 1, "confirm_time": nxt["t"]}
        elif closed_inside:
            if nxt["c"] < nxt["o"] and nxt["c"] < brk["c"] and nxt["c"] < line_n:
                found = {"type": "break_sweep", "dir": "bear", "level": line_b,
                         "extreme": brk["h"], "break_idx": b, "confirm_idx": b + 1,
                         "confirm_time": nxt["t"]}

    return found


def tech_detect_break(c5, channel, bias_dir):
    """Busca rupturas en techo y suelo; respeta la dirección de H4."""

    results = []

    up = tech_detect_break_up(c5, channel["upper"])
    if up:
        up["boundary"] = "resistencia"
        results.append(up)

    down = tech_detect_break_up(tech_mirror_candles(c5), tech_mirror_line(channel["lower"]))
    if down:
        down["dir"] = "bear" if down["dir"] == "bull" else "bull"
        down["level"] = -down["level"]
        down["extreme"] = -down["extreme"]
        down["boundary"] = "soporte"
        results.append(down)

    allowed = []

    for item in results:
        if bias_dir in ("bull", "bear") and item["dir"] != bias_dir:
            continue
        allowed.append(item)

    if not allowed:
        return None

    allowed.sort(key=lambda r: r["confirm_idx"])
    return allowed[-1]


# ------------------------------------------------------------
# Noticias de impacto medio/alto en el momento de la alerta
# ------------------------------------------------------------

async def tech_news_for(cfg, now):
    """Noticias medias/altas de las divisas del activo, sólo si existen en la ventana."""

    today = now.astimezone(CALENDAR_TZ).date()
    events = []

    for impact in ("high", "medium"):
        try:
            batch = await fetch_calendar_events(today - timedelta(days=1), today + timedelta(days=1), impact=impact)
        except Exception as error:
            logger.warning("Alertas técnicas: no se pudo leer el calendario (%s)", error)
            batch = None

        events.extend(batch or [])

    found, seen = [], set()

    for event in events:
        impact = str(event_value(event, "impact", "importance")).lower()

        if impact not in ("high", "medium"):
            continue

        if event_currency(event).upper() not in cfg["ccy"]:
            continue

        moment = event_datetime_utc(event)

        if not moment:
            continue

        minutes = (moment - now).total_seconds() / 60

        if not (-TECH_NEWS_BEHIND_MINUTES <= minutes <= TECH_NEWS_AHEAD_MINUTES):
            continue

        key = (str(event_value(event, "name", "title", "event")), event_currency(event), moment.isoformat())

        if key in seen:
            continue

        seen.add(key)
        found.append((moment, minutes, impact, event))

    found.sort(key=lambda item: (item[2] != "high", abs(item[1])))
    return sorted(found[:3], key=lambda item: item[0])


def tech_news_lines(news):
    if not news:
        return [], False

    lines = ["📰 <b>Noticia en la ventana</b>"]
    danger = False

    for moment, minutes, impact, event in news:
        name = str(event_value(event, "name", "title", "event") or "Evento económico")
        icon = "🔴" if impact == "high" else "🟠"
        label = "alto" if impact == "high" else "medio"

        if minutes > 1:
            when = f"en ~{int(round(minutes))} min"
        elif minutes >= -1:
            when = "publicándose ahora"
        else:
            when = f"hace ~{int(round(-minutes))} min"

        extra = []
        consensus = event_value(event, "consensus", "forecast", "expected")
        prior = event_value(event, "prior", "previous")
        actual = event_value(event, "actual")

        if actual:
            extra.append(f"actual {escape(str(actual))}")
        if consensus:
            extra.append(f"consenso {escape(str(consensus))}")
        if prior:
            extra.append(f"anterior {escape(str(prior))}")

        tail = f" ({' · '.join(extra)})" if extra else ""
        lines.append(
            f"{icon} <b>{escape(event_currency(event).upper() or 'N/D')}</b> · {escape(name)} "
            f"— impacto {label}, {when}{tail}"
        )

        if impact == "high" and -TECH_NEWS_DANGER_MINUTES <= minutes <= TECH_NEWS_DANGER_MINUTES:
            danger = True

    if danger:
        lines.append(
            "⛔ <b>Riesgo elevado:</b> hay un evento de alto impacto muy cerca. "
            "El precio puede barrer niveles en ambos sentidos y los patrones técnicos pierden fiabilidad."
        )
    else:
        lines.append(
            "ℹ️ Las noticias pueden aumentar la volatilidad y invalidar el escenario técnico."
        )

    return lines, danger


# ------------------------------------------------------------
# Mensaje de la alerta
# ------------------------------------------------------------

def tech_session_open(cfg, now):
    if cfg["kind"] == "crypto":
        return True

    if now.weekday() >= 5:
        return False

    return TECH_ACTIVE_START_UTC <= now.hour < TECH_ACTIVE_END_UTC


def tech_session_bonus(cfg, now):
    if cfg["kind"] == "crypto":
        return True

    return now.weekday() < 5 and 7 <= now.hour < 17


def tech_tradingview_url(cfg, interval="5"):
    return "https://www.tradingview.com/chart/?" + urlencode({"symbol": cfg["tv"], "interval": interval})


def tech_zone_text(zone, fmt):
    names = {"FVG": "Imbalance (FVG)", "OB": "Order Block (OB)", "LIQ": "Liquidez"}
    side = "demanda" if zone["side"] == "demand" else "oferta"
    text = f"{names.get(zone['kind'], zone['kind'])} de {side} {fmt(zone['low'])}–{fmt(zone['high'])}"

    if zone["kind"] == "LIQ":
        what = "mínimos" if zone["side"] == "demand" else "máximos"
        equal = " (equal " + ("lows" if zone["side"] == "demand" else "highs") + ")" if zone.get("equal") else ""
        text = f"Liquidez de {what} H1 en {fmt(zone['level'])}{equal}"
    elif zone.get("conf"):
        text += " + confluencia de liquidez"

    return text


def build_tech_alert(name, cfg, setup, bias, price, ref_liquidity, news_lines, now):
    digits = cfg["digits"]

    def fmt(value):
        return f"{value:.{digits}f}"

    bull = setup["dir"] == "bull"
    arrow = "🟢" if bull else "🔴"
    scenario = "alcista" if bull else "bajista"
    h4_text = bias.get("label") or "Neutral / rango"

    if setup["type"] == "smc":
        title = "ALERTA TÉCNICA · BARRIDO DE LIQUIDEZ EN ZONA H1"
        what_swept = "mínimos" if bull else "máximos"
        lines = [
            f"🔔 <b>{title}</b>",
            "",
            f"{cfg['emoji']} <b>{escape(name)}</b> · {arrow} Escenario {scenario} a favor de H4",
            _alert_time_line(now),
            "",
            f"📊 <b>H4 (dirección):</b> {escape(h4_text)}",
            f"💧 <b>H1 (zona):</b> {escape(tech_zone_text(setup['zone'], fmt))}",
            "",
            "⚡ <b>M5 (entrada/POI):</b>",
            f"✅ Barrido de liquidez de {what_swept} en {fmt(setup['extreme'])} "
            f"(nivel barrido: {fmt(setup['level'])})",
            "✅ Cierre de vela a favor recuperando el nivel",
            f"✅ Vela de confirmación {scenario} ({setup['confirm_time']:%H:%M} UTC)"
        ]
    else:
        real = setup["type"] == "break_real"
        title = (
            "ALERTA TÉCNICA · RUPTURA CONFIRMADA"
            if real else "ALERTA TÉCNICA · BARRIDO EN SOPORTE/RESISTENCIA"
        )
        channel = setup.get("channel_kind", "Rango")
        boundary = setup.get("boundary", "nivel")

        if real:
            detail = (
                f"✅ Ruptura de la {boundary} ({fmt(setup['level'])}) con cierre de vela fuera del {channel.lower()}",
                f"✅ Vela de continuación {scenario} que se mantiene fuera"
            )
        else:
            detail = (
                f"✅ Mecha/ruptura de la {boundary} ({fmt(setup['level'])}) que NO se sostiene: barrido de liquidez",
                f"✅ Cierre de vela de vuelta dentro y vela de continuación {scenario}"
            )

        lines = [
            f"🔔 <b>{title}</b>",
            "",
            f"{cfg['emoji']} <b>{escape(name)}</b> · {arrow} Escenario {scenario}",
            _alert_time_line(now),
            "",
            f"📊 <b>H4 (dirección):</b> {escape(h4_text)}",
            f"📐 <b>H1:</b> {escape(channel)} "
            f"({fmt(setup['l_now'])} – {fmt(setup['u_now'])})",
            "",
            "⚡ <b>M5:</b>",
            detail[0],
            detail[1]
        ]

    extras = []

    if setup.get("choch"):
        extras.append("cambio de estructura menor (CHoCH/BOS) en M5")
    if setup.get("vol_ok"):
        extras.append("volumen por encima de la media")
    if setup.get("pd_ok"):
        extras.append("precio en " + ("descuento" if bull else "premium") + " del rango H4")
    if setup.get("zone_conf"):
        extras.append("zona con confluencia (OB/FVG + liquidez)")
    if setup.get("session_ok"):
        extras.append("sesión de alta liquidez")
    if setup.get("quality_ok"):
        extras.append("rango/canal bien definido (≥6 toques)")

    lines.append("")
    lines.append(f"🎯 <b>Confluencias:</b> {setup['score']}/{setup['score_max']}")

    if extras:
        lines.append("➕ " + " · ".join(extras))

    lines.extend([
        "",
        "📍 <b>Niveles de referencia</b> (informativos)",
        f"• Precio actual: <b>{fmt(price)}</b>",
        f"• Nivel que invalida el escenario: {'bajo' if bull else 'sobre'} <b>{fmt(setup['extreme'])}</b>"
    ])

    if ref_liquidity is not None:
        lines.append(
            f"• Liquidez H1 cercana: {fmt(ref_liquidity)} "
            f"({'máximos' if bull else 'mínimos'} sin barrer)"
        )

    if news_lines:
        lines.append("")
        lines.extend(news_lines)

    if tech_symbol_scale(name, cfg) != 1.0:
        lines.extend([
            "",
            f"ℹ️ Niveles aproximados (referencia {escape(str(TECH_STATE.get('td_sym', {}).get(name, '')))}"
            f" ×{tech_symbol_scale(name, cfg):g}); contrasta con tu gráfico y tu broker."
        ])

    lines.extend([
        "",
        TECH_RISK_BASE,
        f"📌 {escape(cfg['risk'])}",
        "",
        '📊 Datos: <a href="https://twelvedata.com">Twelve Data</a>'
    ])

    return "\n".join(lines)[:4000]


# ------------------------------------------------------------
# Control de envío (duplicados, enfriamiento y topes diarios)
# ------------------------------------------------------------

def tech_can_send(name, key, now):
    _tech_roll_day()

    if key in TECH_STATE["sent"]:
        return False, "duplicada"

    last = TECH_STATE["last_alert"].get(name)

    if last:
        try:
            elapsed = (now - datetime.fromisoformat(last)).total_seconds() / 60
            if elapsed < TECH_COOLDOWN_MINUTES:
                return False, f"enfriamiento ({int(TECH_COOLDOWN_MINUTES - elapsed)} min)"
        except ValueError:
            pass

    daily = TECH_STATE["daily"]

    if daily.get("total", 0) >= TECH_MAX_PER_DAY:
        return False, "tope diario alcanzado"

    if daily.get("by_symbol", {}).get(name, 0) >= TECH_MAX_PER_SYMBOL_DAY:
        return False, "tope diario del activo"

    return True, ""


def tech_register_sent(name, key, setup, now):
    TECH_STATE["sent"][key] = now.isoformat()
    TECH_STATE["last_alert"][name] = now.isoformat()
    daily = TECH_STATE["daily"]
    daily["total"] = daily.get("total", 0) + 1
    daily.setdefault("by_symbol", {})[name] = daily.get("by_symbol", {}).get(name, 0) + 1
    TECH_STATE["history"].append({
        "t": now.isoformat(), "symbol": name, "type": setup["type"], "dir": setup["dir"]
    })


async def tech_notify_admin_once(application, key, text):
    _tech_roll_day()
    full_key = f"{key}|{_tech_today()}"

    if full_key in TECH_STATE["notified"] or not ADMIN_TELEGRAM_ID:
        return

    TECH_STATE["notified"][full_key] = True

    try:
        await application.bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=text, parse_mode="HTML")
    except Exception as error:
        logger.warning("No se pudo avisar al administrador: %s", error)


async def tech_publish(application, text, url):
    channel_id = get_community_channel_id()

    if not channel_id:
        raise TechDataError("el canal todavía no está detectado")

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📈 Abrir gráfico (TradingView)", url=url)]])

    for attempt in range(2):
        try:
            await application.bot.send_message(
                chat_id=channel_id, text=text, parse_mode="HTML",
                disable_web_page_preview=True, reply_markup=markup
            )
            return
        except RetryAfter as error:
            if attempt == 1:
                raise
            await asyncio.sleep(float(getattr(error, "retry_after", 5)) + 1)


# ------------------------------------------------------------
# Escaneo por activo
# ------------------------------------------------------------

def tech_symbol_candidates(name, cfg):
    """Símbolos a probar para un activo: primero el que ya funcionó, luego el resto."""
    items = [(cfg["td"], 1.0)] + [(sym, float(k)) for sym, k in cfg.get("td_alts", [])]
    good = TECH_STATE.get("td_sym", {}).get(name)
    items.sort(key=lambda it: 0 if it[0] == good else 1)
    bad = TECH_STATE.get("td_bad", {})
    now = time.time()
    live = [it for it in items if bad.get(f"{name}|{it[0]}", 0) <= now]
    return live or items


def tech_symbol_scale(name, cfg):
    """Factor de escala del símbolo en uso (1.0 = símbolo directo)."""
    used = TECH_STATE.get("td_sym", {}).get(name)
    for sym, k in cfg.get("td_alts", []):
        if sym == used:
            return float(k)
    return 1.0


def tech_scale_candles(candles, scale):
    if not scale or scale == 1.0:
        return candles
    return [
        {**c, "o": c["o"] * scale, "h": c["h"] * scale, "l": c["l"] * scale, "c": c["c"] * scale}
        for c in candles
    ]


async def tech_refresh(name, cfg, frame):
    rt = TECH_RUNTIME.setdefault(name, {})
    spec = {"h4": ("4h", 14400, 160), "h1": ("1h", 3600, 200), "m5": ("5min", 300, 150)}[frame]
    errors = []

    for symbol, scale in tech_symbol_candidates(name, cfg):
        try:
            candles = await td_get_candles(symbol, spec[0], spec[2])
        except TechSymbolError as error:
            errors.append(f"{symbol}: {str(error)[:90]}")
            TECH_STATE["td_bad"][f"{name}|{symbol}"] = time.time() + 5 * 3600
            logger.warning("Twelve Data: %s no disponible para %s (%s)", symbol, name, error)
            continue

        if rt.get("td_used") not in (None, symbol):
            # Cambió la fuente de datos: se descartan velas y zonas calculadas con la anterior
            for key in ("h4", "h1", "m5", "h4_ts", "h1_ts", "m5_ts", "bias", "zones", "channel", "a1"):
                rt.pop(key, None)

        rt["td_used"] = symbol
        if TECH_STATE.get("td_sym", {}).get(name) != symbol:
            TECH_STATE.setdefault("td_sym", {})[name] = symbol
            tech_state_save()
            logger.info("Twelve Data: %s usa el símbolo %s (escala %s)", name, symbol, scale)

        rt[frame] = tech_closed_candles(tech_scale_candles(candles, scale), spec[1])
        rt[frame + "_ts"] = time.time()
        return rt[frame]

    raise TechSymbolError(" | ".join(errors) or "sin símbolo disponible")


def tech_price_is_near(rt, price):
    a1 = rt.get("a1")

    if not a1 or price is None:
        return False

    bias = rt.get("bias") or {}
    want = {"bull": "demand", "bear": "supply"}.get(bias.get("dir"))

    for zone in rt.get("zones", []):
        if want and zone["side"] != want:
            continue
        if zone["low"] - 1.0 * a1 <= price <= zone["high"] + 1.0 * a1:
            return True

    channel = rt.get("channel")

    if channel and (
        abs(price - channel["u_now"]) <= a1 or abs(price - channel["l_now"]) <= a1
    ):
        return True

    return False


def tech_score_smc(cfg, setup, bias, price, now):
    parts = 0
    maximum = 4 + (1 if setup["vol_known"] else 0)
    zone = setup["zone"]

    setup["zone_conf"] = bool(zone.get("conf") or zone["kind"] in ("OB", "FVG"))
    setup["session_ok"] = tech_session_bonus(cfg, now)
    setup["pd_ok"] = False

    rng = bias.get("range")
    if rng and rng[1] > rng[0]:
        eq = (rng[0] + rng[1]) / 2
        setup["pd_ok"] = price <= eq if setup["dir"] == "bull" else price >= eq

    for flag in (setup["zone_conf"], setup["session_ok"], setup["pd_ok"], setup.get("choch")):
        parts += 1 if flag else 0

    if setup["vol_known"] and setup["vol_ok"]:
        parts += 1

    setup["score"], setup["score_max"] = parts, maximum
    return parts


def tech_score_break(cfg, setup, bias, channel, c5, now):
    avg = [c["v"] for c in c5[-60:] if c["v"] > 0]
    avg_vol = (sum(avg) / len(avg)) if len(avg) >= 20 else 0
    known = avg_vol > 0
    maximum = 3 + (1 if known else 0)
    parts = 0

    setup["session_ok"] = tech_session_bonus(cfg, now)
    setup["quality_ok"] = channel["touches"] >= 6
    aligned = bias.get("dir") == setup["dir"]
    setup["pd_ok"] = False
    setup["vol_known"] = known
    setup["vol_ok"] = known and max(
        c5[setup["break_idx"]]["v"], c5[setup["confirm_idx"]]["v"]
    ) > 1.3 * avg_vol

    for flag in (setup["session_ok"], setup["quality_ok"], aligned):
        parts += 1 if flag else 0

    if known and setup["vol_ok"]:
        parts += 1

    setup["score"], setup["score_max"] = parts, maximum
    setup["channel_kind"] = channel["kind"]
    setup["u_now"], setup["l_now"] = channel["u_now"], channel["l_now"]
    return parts


async def tech_scan_symbol(application, name, force=False):
    cfg = TECH_SYMBOLS[name]
    rt = TECH_RUNTIME.setdefault(name, {})
    now = datetime.now(timezone.utc)

    disabled = TECH_STATE["disabled"].get(name)

    if disabled and disabled.get("until", 0) > time.time():
        rt["status"] = f"⏸️ en pausa: {disabled.get('reason', '')[:60]}"
        return

    if not force and not tech_session_open(cfg, now):
        rt["status"] = "🌙 fuera del horario de análisis"
        return

    try:
        if force or time.time() - rt.get("h4_ts", 0) > TECH_H4_TTL_SECONDS:
            c4 = await tech_refresh(name, cfg, "h4")
            rt["bias"] = tech_h4_bias(c4)

        if force or time.time() - rt.get("h1_ts", 0) > TECH_H1_TTL_SECONDS:
            c1 = await tech_refresh(name, cfg, "h1")
            rt["zones"], rt["a1"] = tech_h1_zones(c1)
            rt["channel"] = tech_h1_channel(c1)
    except TechSymbolError as error:
        TECH_STATE["disabled"][name] = {"until": time.time() + 6 * 3600, "reason": str(error)}
        rt["status"] = f"⛔ símbolo no disponible: {str(error)[:80]}"
        await tech_notify_admin_once(
            application, f"symbol|{name}",
            f"⚠️ <b>Alertas técnicas:</b> no se pudo leer <b>{escape(name)}</b> "
            f"en Twelve Data (probado: <code>"
            f"{escape(', '.join([cfg['td']] + [a for a, _ in cfg.get('td_alts', [])]))}</code>).\n"
            f"<i>{escape(str(error)[:200])}</i>\n\n"
            "Puede requerir otro plan o símbolo (variables TECH_SYMBOL_US30 / TECH_SYMBOL_US30_ALT). "
            "Se reintenta en 6 horas."
        )
        return
    except TechRateLimit:
        rt["status"] = "⏳ límite por minuto de Twelve Data; se reintenta"
        await asyncio.sleep(30)
        return

    bias = rt.get("bias") or {"dir": "neutral", "label": "Neutral / rango"}
    channel = rt.get("channel")
    zones = rt.get("zones") or []
    h1_candles = rt.get("h1") or []

    if bias["dir"] == "neutral" and not channel:
        rt["status"] = f"⚪ H4 neutral ({bias.get('reason', 'sin sesgo')}) y sin rango/canal H1 · en espera"
        return

    last_price = rt["m5"][-1]["c"] if rt.get("m5") else (h1_candles[-1]["c"] if h1_candles else None)
    near = tech_price_is_near(rt, last_price)
    interval = TECH_M5_NEAR_SECONDS if near else TECH_M5_FAR_SECONDS

    if not force and time.time() - rt.get("m5_ts", 0) < interval:
        return

    c5 = await tech_refresh(name, cfg, "m5")

    if not c5 or (now - c5[-1]["t"]).total_seconds() > 25 * 60:
        rt["status"] = "💤 sin velas M5 recientes (mercado cerrado o datos retrasados)"
        return

    price = c5[-1]["c"]
    near = tech_price_is_near(rt, price)
    candidates = []

    if bias["dir"] in ("bull", "bear") and zones:
        setup = tech_detect_smc(c5, zones, bias["dir"], rt.get("a1"))
        if setup:
            tech_score_smc(cfg, setup, bias, price, now)
            candidates.append(setup)

    if channel:
        setup = tech_detect_break(c5, channel, bias["dir"])
        if setup:
            tech_score_break(cfg, setup, bias, channel, c5, now)
            candidates.append(setup)

    state_icon = {"bull": "🟢", "bear": "🔴"}.get(bias["dir"], "⚪")
    extra = f" · {channel['kind'].lower()} H1" if channel else ""
    rt["status"] = (
        f"{state_icon} H4 {bias.get('label', '')} · {len(zones)} zonas H1{extra} · "
        f"M5 {'cerca de zona' if near else 'lejos de zonas'}, en espera"
    )

    if not candidates:
        return

    candidates.sort(key=lambda s: (s["score"], s["confirm_idx"]), reverse=True)
    setup = candidates[0]

    if setup["score"] < TECH_MIN_SCORE:
        rt["status"] += f" · patrón detectado sin confluencias suficientes ({setup['score']}/{setup['score_max']})"
        return

    key = f"{name}|{setup['type']}|{setup['dir']}|{setup['confirm_time'].isoformat()}"
    allowed, reason = tech_can_send(name, key, now)

    if not allowed:
        rt["status"] += f" · alerta no enviada: {reason}"
        return

    news = await tech_news_for(cfg, now)
    news_lines, _ = tech_news_lines(news)
    ref = tech_next_liquidity(h1_candles, price, "up" if setup["dir"] == "bull" else "down")
    text = build_tech_alert(name, cfg, setup, bias, price, ref, news_lines, now)

    try:
        await tech_publish(application, text, tech_tradingview_url(cfg))
    except Exception as error:
        logger.error("No se pudo publicar la alerta técnica de %s: %s", name, error)
        rt["status"] += f" · error al publicar: {str(error)[:60]}"
        return

    tech_register_sent(name, key, setup, now)
    tech_state_save()
    rt["status"] = f"✅ alerta enviada ({setup['type']}, {setup['dir']})"
    logger.info("🔔 Alerta técnica enviada: %s %s %s", name, setup["type"], setup["dir"])


async def tech_scan_all(application, force=False):
    for name in TECH_SYMBOLS:
        try:
            await tech_scan_symbol(application, name, force=force)
        except asyncio.CancelledError:
            raise
        except TechBudgetError:
            TECH_RUNTIME.setdefault(name, {})["status"] = "📉 presupuesto diario de Twelve Data agotado"
            await tech_notify_admin_once(
                application, "budget",
                "⚠️ <b>Alertas técnicas:</b> se agotó el presupuesto diario de Twelve Data. "
                "El análisis se reanuda a las 00:00 UTC."
            )
            break
        except TechDataError as error:
            TECH_RUNTIME.setdefault(name, {})["status"] = f"⚠️ {str(error)[:90]}"
            logger.warning("Alertas técnicas %s: %s", name, error)
        except Exception as error:
            TECH_RUNTIME.setdefault(name, {})["status"] = f"⚠️ error interno: {str(error)[:80]}"
            logger.error("Alertas técnicas %s: %s", name, error, exc_info=True)

    tech_state_save()


async def tech_alerts_monitor(application):
    tech_state_load()

    if not TWELVEDATA_API_KEY:
        logger.warning("Alertas técnicas desactivadas: falta TWELVEDATA_API_KEY.")

    await asyncio.sleep(15)

    while True:
        try:
            if TWELVEDATA_API_KEY and TECH_STATE.get("enabled", True):
                await tech_scan_all(application)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("Error en el monitor de alertas técnicas: %s", error, exc_info=True)

        await asyncio.sleep(TECH_TICK_SECONDS)


# ------------------------------------------------------------
# Administración de las alertas técnicas
# ------------------------------------------------------------

def tech_admin_keyboard():
    enabled = TECH_STATE.get("enabled", True)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualizar estado", callback_data="admin_tech")],
        [InlineKeyboardButton("🔎 Escanear ahora", callback_data="admin_tech_scan")],
        [InlineKeyboardButton("⏸️ Pausar alertas" if enabled else "▶️ Activar alertas",
                              callback_data="admin_tech_toggle")],
        [InlineKeyboardButton("🔙 Administración", callback_data="admin_menu")]
    ])


async def show_admin_tech(query):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return

    _tech_roll_day()
    enabled = TECH_STATE.get("enabled", True)
    daily = TECH_STATE["daily"]

    lines = [
        "🧭 <b>ALERTAS TÉCNICAS APEXQUANT</b>",
        "",
        f"Estado: {'🟢 activas' if enabled else '⏸️ en pausa'}"
        + ("" if TWELVEDATA_API_KEY else " · ⚠️ falta TWELVEDATA_API_KEY"),
        f"📡 Créditos Twelve Data hoy: <b>{tech_budget_used()}/{TD_DAILY_BUDGET}</b>",
        f"🔔 Alertas hoy: <b>{daily.get('total', 0)}/{TECH_MAX_PER_DAY}</b> "
        f"(máx. {TECH_MAX_PER_SYMBOL_DAY} por activo)",
        f"🎚️ Confluencias mínimas: {TECH_MIN_SCORE} · enfriamiento: {TECH_COOLDOWN_MINUTES} min",
        f"🕒 Horario de análisis (UTC, lun–vie): {TECH_ACTIVE_START_UTC:02d}:00–{TECH_ACTIVE_END_UTC:02d}:00 · BTC 24/7",
        ""
    ]

    for name, cfg in TECH_SYMBOLS.items():
        rt = TECH_RUNTIME.get(name, {})
        source = ""
        if tech_symbol_scale(name, cfg) != 1.0:
            source = f" · fuente: {TECH_STATE.get('td_sym', {}).get(name, '')} ×{tech_symbol_scale(name, cfg):g}"
        lines.append(
            f"{cfg['emoji']} <b>{escape(name)}</b>: {escape(rt.get('status', 'sin análisis todavía'))}{escape(source)}"
        )

    history = TECH_STATE.get("history", [])[-3:]

    if history:
        lines.append("")
        lines.append("🕘 <b>Últimas alertas</b>")
        for item in reversed(history):
            lines.append(f"• {escape(str(item.get('t', ''))[:16].replace('T', ' '))} UTC · "
                         f"{escape(str(item.get('symbol')))} · {escape(str(item.get('type')))} · {escape(str(item.get('dir')))}")

    try:
        await query.edit_message_text(
            "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=tech_admin_keyboard()
        )
    except BadRequest as error:
        if "not modified" in str(error).lower():
            await query.answer("Sin cambios desde la última actualización.")
        else:
            raise


async def admin_tech_toggle(query):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return

    TECH_STATE["enabled"] = not TECH_STATE.get("enabled", True)
    tech_state_save()
    await show_admin_tech(query)


async def admin_tech_scan(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Acceso restringido.", show_alert=True)
        return

    if not TWELVEDATA_API_KEY:
        await query.edit_message_text(
            "⚠️ Falta la variable TWELVEDATA_API_KEY en Deployka.",
            reply_markup=tech_admin_keyboard()
        )
        return

    await query.edit_message_text(
        "🔎 Escaneo iniciado en segundo plano. Consume unos 15 créditos de Twelve Data y "
        "puede tardar 1–3 minutos por el límite por minuto.\n\n"
        "Pulsa «Actualizar estado» para ver el resultado.",
        reply_markup=tech_admin_keyboard()
    )

    task = asyncio.create_task(tech_scan_all(context.application, force=True))
    _TECH_TASKS.add(task)
    task.add_done_callback(_TECH_TASKS.discard)


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

ONEROYAL — COPYTRADING, COMISIONES Y BONO TRADEABLE
Para las respuestas sobre la oferta de ApexQuant, explica que el esquema previsto es
70% de las ganancias sujetas a comisión para el usuario y 30% para ApexQuant. No hay
cuota de entrada ni cuota fija de gestión; si no hay ganancias sujetas a comisión, no
se genera comisión de rendimiento. Aclara que la configuración efectiva debe coincidir
con lo que muestra la oferta de OneRoyal.
La comisión del 30% de ApexQuant en CopyTrading ya está configurada en OneRoyal.
Para agentes adicionales, el administrador de ApexQuant configura manualmente un 20%
sobre la parte de comisión de ApexQuant. No es el 20% de las ganancias totales del
seguidor. Si ApexQuant recibe el 30% de una base sujeta a comisión, el 20% de esa parte
equivale al 6% de esa misma base. Los pasos completos para ser agente adicional están
en la sección «PASOS PARA SER AGENTE ADICIONAL (SUB-IB)» más abajo.
Sobre OneRoyal, distingue la entidad regulada y jurisdicción del cliente: el grupo menciona
ASIC, CySEC, VFSC y FSA de San Vicente y las Granadinas para entidades diferentes. Nunca
digas que todas las licencias protegen a todos los clientes.
En la página internacional consultada, OneRoyal publica ECN con spreads desde 0.0 pips y
comisión de USD 3.50 por lado por lote; Classic con comisión cero y spreads desde 1.4 pips.
Son cifras orientativas que pueden variar por país, entidad y tipo de cuenta.
El manager de ApexQuant compartió estos ejemplos de bono tradeable: depósito USD 300,
bono USD 300; depósito USD 1,000, bono USD 500. Explica que requieren verificación, elección
de cuenta elegible y aceptación de términos. El bono no es retirable; las ganancias pueden
ser retirables bajo condiciones. La promoción puede variar y el retiro de fondos puede
afectar/eliminar el bono. Recomienda confirmar los términos vigentes en el portal antes
de depositar. No inventes reglas que no estén confirmadas.

ONEROYAL — REFERIDOS, IB, SUB-IB Y PUBLIC AGENT
La información oficial consultada indica que los IB pueden usar enlaces
personalizados, seguir clientes y comisiones mediante herramientas del portal,
y que existe una estructura Master IB/Sub-IB sujeta a aprobación y condiciones.
PASOS PARA SER AGENTE ADICIONAL (SUB-IB) DE APEXQUANT (menú Referidos). Explícalos en
este orden cuando alguien pregunte; son confirmados por el soporte de OneRoyal:
1) Registrarse en OneRoyal con el enlace IB de ApexQuant (botón «Registrarme con
   OneRoyal») y verificar la cuenta. Así quedan como clientes directos de ApexQuant.
   Siempre lo primero es estar registrado como directo de ApexQuant.
2) En el menú Cuentas de OneRoyal, crear una cuenta ECN principal (fondeada). Ahí
   depositan fondos para operar o para el CopyTrading, conectándose con el enlace de
   proveedor de ApexQuant (botón «Seguir Apex Quant»). Un cliente que solo quiere copiar
   la estrategia únicamente necesita los pasos 1 y 2: se registra bajo el link de
   referido, se verifica, crea la cuenta, deposita y se une al copy.
3) Solicitar convertirse también en IB, contactando a soporte de OneRoyal por e-mail o
   por el soporte interno. Es necesario antes de pedir el enlace de agente adicional.
4) Ya como IB, crear en el mismo menú Cuentas una segunda cuenta ECN, aparte de la
   cuenta fondeada que participa en el CopyTrading. Esa segunda cuenta es la que recibe
   el performance fee de sus clientes directos.
5) Contactar al administrador de ApexQuant con el botón «Contactar al manager de
   ApexQuant» del menú Referidos, con los pasos anteriores completos, para solicitar su
   enlace de agente (adicional/público). Deben enviar de forma privada el número de la
   segunda cuenta ECN. El administrador crea manualmente el enlace, lo asocia a esa
   cuenta, y coloca ese número en la configuración de la campaña para que el agente
   reciba la comisión por sus clientes directos. El porcentaje que se reparte al agente
   se estipula en el enlace que el administrador le crea.
El bot no crea enlaces ni asigna comisiones. Nunca pidas contraseñas, códigos de acceso
ni otros datos de autenticación. No inventes ni fabriques URLs de agentes.
Si la pregunta sobre referidos, IB, Sub-IB o agentes no queda resuelta con esta
información, o el usuario sigue con dudas, sugiere contactar al administrador de
ApexQuant con el botón «Contactar al manager de ApexQuant» del menú Referidos.

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

TÉRMINOS Y CONDICIONES DE COPYTRADING (botón «TÉRMINOS Y CONDICIONES» en el menú CopyTrading)
Estos términos son oficiales: respóndelos con fidelidad y no prometas nada que excluyan.
- Filosofía: la metodología se basa en paciencia, disciplina y selección cuidadosa de
  oportunidades. ApexQuant no opera por obligación, aburrimiento ni impaciencia. Pueden pasar
  uno o varios días sin abrir operaciones; eso no significa que la estrategia falle o que el
  sistema se haya detenido.
- Órdenes pendientes: el precio puede acercarse a pocos pips de la zona y girar sin activar la
  orden. Prefieren perder esa oportunidad antes que entrar fuera de plan. No persiguen el
  precio ni entran tarde solo porque el mercado se mueva. Las órdenes pendientes no garantizan
  que el precio llegue, que se ejecuten ni que el mercado se comporte como se espera.
- Riesgo: toda operación puede perder, aunque el análisis sea correcto. El Stop Loss limita la
  pérdida pero no garantiza el importe exacto (deslizamiento, gaps, liquidez excepcional). La
  metodología no elimina el riesgo ni garantiza preservar el capital.
- Expectativas del seguidor: no hay cantidad mínima de operaciones, ni frecuencia determinada,
  ni beneficios diarios/semanales/mensuales, ni rentabilidad, tasa de aciertos o ausencia de
  pérdidas garantizadas. Los resultados de la cuenta seguidora pueden diferir de los del
  proveedor (ejecución, spreads, deslizamiento, configuración de la cuenta, instrumentos
  disponibles, requisitos del bróker).
- No se fuerzan operaciones para mostrar actividad, compensar un periodo sin entradas ni
  recuperar una pérdida anterior. Cada oportunidad se evalúa por sus propios méritos.
- Responsabilidad: el usuario debe valorar su horizonte temporal, expectativas y tolerancia al
  riesgo; la estrategia puede no ser adecuada para quien espera operaciones diarias o
  resultados inmediatos. La ausencia de operaciones no garantiza una entrada rentable y una
  operación no ejecutada no habría sido necesariamente ganadora. Debe revisar las condiciones
  de OneRoyal, las comisiones y los riesgos del trading apalancado, y participar solo con
  capital que pueda permitirse perder (nunca dinero para gastos esenciales u obligaciones).
- Comisiones: ApexQuant participa con el 30% sobre las ganancias elegibles del CopyTrading,
  según el cálculo y liquidación de OneRoyal. Mantener la cuenta vinculada sin ganancias
  elegibles no genera beneficios. Otras tarifas o costes del bróker deben consultarse con
  OneRoyal.
- El usuario reconoce: pueden pasar días sin operaciones; algunas oportunidades quedan sin
  ejecutar; las operaciones pueden cerrar en pérdida (incluido el Stop Loss); no hay garantía
  de beneficios ni de recuperar pérdidas; sus resultados pueden diferir de los del proveedor;
  es responsable de evaluar su situación financiera; debe revisar y aceptar las condiciones de
  OneRoyal y de la plataforma de CopyTrading.
- Los términos no garantizan resultados ni sustituyen las condiciones contractuales de
  OneRoyal, la documentación oficial ni el asesoramiento financiero independiente.
Cuando pregunten por frecuencia de operaciones, días sin operar, órdenes que no se activan,
Stop Loss, resultados, comisiones o expectativas del CopyTrading, responde conforme a estos
términos. Si algo no está cubierto, dilo y recomienda revisar OneRoyal o contactar al manager
de ApexQuant. Indica que pueden leer el texto completo en CopyTrading → «TÉRMINOS Y
CONDICIONES».

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

FORMATO DE RESPUESTA (obligatorio)
- Entrega UNA sola respuesta final. Nunca ofrezcas "Opción 1", "Opción 2" ni
  versiones alternativas, ni expliques cómo redactaste la respuesta.
- Telegram no muestra fórmulas. No uses LaTeX, ni símbolos $...$, ni comandos con
  barra invertida (\\uparrow, \\downarrow, \\rightarrow). Para flechas usa ⬆️ ⬇️ ➡️.
- Para destacar títulos o palabras clave usa **negrita** (doble asterisco).
  No uses asteriscos sueltos para cursiva, ni títulos con #, ni tablas, ni líneas ---.
- Para listas usa viñetas con guion "- " o numeración "1.", una idea por línea.
- Separa las secciones con una línea en blanco y mantén los párrafos cortos.
"""

# ------------------------------------------------------------
# LIMPIEZA Y FORMATO DE LAS RESPUESTAS DEL ASISTENTE
# ------------------------------------------------------------
# Gemma escribe en Markdown y a veces en LaTeX (ej.: $\uparrow$).
# Telegram no entiende ninguno de los dos, así que aquí se convierten
# las flechas/símbolos en emojis y el Markdown en HTML real de Telegram.
# Si Telegram rechazara el formato, se reenvía en texto plano.

ASSISTANT_LATEX_SYMBOLS = {
    "uparrow": "⬆️", "Uparrow": "⬆️", "upwardarrow": "⬆️",
    "downarrow": "⬇️", "Downarrow": "⬇️",
    "rightarrow": "➡️", "Rightarrow": "➡️", "to": "➡️", "longrightarrow": "➡️",
    "leftarrow": "⬅️", "Leftarrow": "⬅️",
    "leftrightarrow": "↔️", "Leftrightarrow": "↔️",
    "approx": "≈", "times": "×", "cdot": "·", "pm": "±",
    "geq": "≥", "ge": "≥", "leq": "≤", "le": "≤", "neq": "≠", "ne": "≠",
    "Delta": "Δ", "delta": "Δ", "%": "%", "&": "&", "_": "_", "#": "#",
}

def assistant_clean_latex(text):
    """Convierte LaTeX básico ($\\uparrow$, \\rightarrow...) en símbolos/emojis."""
    def convert_commands(chunk):
        chunk = re.sub(r"\\(?:text|mathrm|mathbf|textbf|mathit)\s*\{([^{}]*)\}", r"\1", chunk)
        chunk = re.sub(
            r"\\([A-Za-z]+|[%&_#])",
            lambda m: ASSISTANT_LATEX_SYMBOLS.get(m.group(1), m.group(1)),
            chunk
        )
        return chunk.replace("{", "").replace("}", "").strip()

    # Fórmulas entre $...$ que contienen comandos LaTeX (los precios como $1.25 no se tocan).
    text = re.sub(
        r"\$\s*([^$\n]*?\\[A-Za-z%&_#][^$\n]*?)\s*\$",
        lambda m: convert_commands(m.group(1)),
        text
    )
    # Comandos LaTeX que hayan quedado sueltos fuera de $...$.
    text = re.sub(
        r"\\(uparrow|Uparrow|downarrow|Downarrow|rightarrow|Rightarrow|leftarrow|Leftarrow|leftrightarrow|approx|times|geq|leq|neq|pm)\b",
        lambda m: ASSISTANT_LATEX_SYMBOLS.get(m.group(1), m.group(1)),
        text
    )
    return text

def assistant_prepare_text(text):
    """Limpia la salida cruda del modelo (sigue siendo Markdown, sin HTML)."""
    text = str(text or "").replace("\r\n", "\n")

    # El modelo a veces entrega varias versiones ("Opción 1 / Opción 2"): se queda solo la primera.
    option2 = re.search(r"(?im)^[^\w\n]*(?:#+\s*)?(?:\*\*)?opci[oó]n\s*2\b", text)
    if option2:
        text = text[:option2.start()]
    text = re.sub(r"(?im)^[^\w\n]*(?:#+\s*)?(?:\*\*)?opci[oó]n\s*1\b[^\n]*\n?", "", text)

    text = assistant_clean_latex(text)

    # ***texto*** (negrita + cursiva) -> **texto**, para no generar etiquetas mal anidadas.
    text = re.sub(r"\*\*\*([^\n*]+?)\*\*\*", r"**\1**", text)

    # Líneas separadoras (---, ***, ___) fuera.
    text = re.sub(r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", "", text)
    # Títulos "### Texto" -> **Texto**
    text = re.sub(
        r"(?m)^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$",
        lambda m: "**" + m.group(1).replace("**", "").strip() + "**",
        text
    )
    # Viñetas "- ", "* ", "+ " -> "• "
    text = re.sub(r"(?m)^(\s*)[-*+]\s+", r"\1• ", text)
    # Espacios y saltos de línea sobrantes.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def assistant_truncate(text, limit=3900):
    text = str(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind("\n\n"), cut.rfind("\n"))
    if boundary > limit * 0.6:
        cut = cut[:boundary]
    return cut.rstrip() + "…"

ASSISTANT_ALLOWED_TAGS = re.compile(r"</?(?:b|i|u|code|pre)>", re.IGNORECASE)

def assistant_markdown_to_html(text):
    """Markdown del modelo -> HTML de Telegram (negrita real, cursiva, código)."""
    text = str(text)
    pieces = []
    last = 0
    # Las etiquetas permitidas (<b>, <code>...) de los avisos del bot se respetan.
    for tag in ASSISTANT_ALLOWED_TAGS.finditer(text):
        pieces.append(escape(text[last:tag.start()], quote=False))
        pieces.append(tag.group(0).lower())
        last = tag.end()
    pieces.append(escape(text[last:], quote=False))
    out = "".join(pieces)

    out = re.sub(r"\*\*([^\n]+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\*\w])\*(?!\s)([^\*\n]+?)(?<!\s)\*(?![\*\w])", r"<i>\1</i>", out)
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    out = out.replace("**", "")  # asteriscos dobles que hayan quedado sin pareja
    return out

def assistant_markdown_to_plain(text):
    """Versión sin ningún formato, para el respaldo automático."""
    out = ASSISTANT_ALLOWED_TAGS.sub("", str(text))
    out = out.replace("**", "")
    out = re.sub(r"(?<![\*\w])\*(?!\s)([^\*\n]+?)(?<!\s)\*(?![\*\w])", r"\1", out)
    out = re.sub(r"`([^`\n]+)`", r"\1", out)
    return out

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
        "macro", "mañana", "hoy", "esta semana", "semana entrante",
        "próxima semana", "proxima semana", "semana que viene", "next week"
    ))

async def assistant_calendar_context(question):
    if not assistant_relevant_calendar(question):
        return ""
    try:
        q = str(question or "").lower()
        next_week = any(k in q for k in (
            "semana entrante", "próxima semana", "proxima semana",
            "semana que viene", "siguiente semana", "next week"
        ))
        max_rows = 12
        if next_week:
            # Lunes a viernes de la próxima semana
            start = date.today() + timedelta(days=(7 - date.today().weekday()))
            end = start + timedelta(days=4)
            max_rows = 30
        elif any(k in q for k in ("esta semana", "semana", "week")):
            start, end = date.today(), date.today() + timedelta(days=6)
            max_rows = 30
        else:
            start, end = today_date(), tomorrow_date()
        events = await fetch_calendar_events(start, end)
        rows = []
        for event in events or []:
            if not isinstance(event, dict):
                continue
            name = str(event_value(event, "name", "title", "event") or "")
            if not name:
                continue
            currency = event_currency(event) or "N/D"
            impact = str(event_value(event, "impact", "importance") or "N/D")
            if (next_week or max_rows > 12) and impact.lower() not in ("high", "alto", "alta", "3", "medium", "medio", "media", "2"):
                continue
            dt = str(event_value(event, "time_utc", "datetime", "date") or "")
            rows.append(f"- {dt} | {impact.upper()} | {currency} | {name}")
            if len(rows) >= max_rows:
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

def assistant_model_chain(primary, extra=None):
    """Modelo principal seguido de los respaldos (y extras opcionales), sin repetir."""
    chain = []
    for m in [primary] + GEMINI_MODEL_FALLBACKS + list(extra or []):
        if m and m not in chain:
            chain.append(m)
    return chain

_DISCOVERED_MODELS_CACHE = {"ts": 0.0, "models": []}

def assistant_discovered_models(api_key):
    """Pregunta a Google qué modelos Gemini 'flash' están disponibles hoy.

    Sirve de red de seguridad cuando los modelos configurados dan 404 (retirados)
    o están saturados. Bloqueante: llamar solo desde un hilo (run_in_executor).
    El resultado se guarda 1 hora en caché.
    """
    import time
    now = time.time()
    if _DISCOVERED_MODELS_CACHE["models"] and now - _DISCOVERED_MODELS_CACHE["ts"] < 3600:
        return list(_DISCOVERED_MODELS_CACHE["models"])

    found = []
    try:
        request = Request(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
            headers={"x-goog-api-key": api_key}
        )
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        for item in data.get("models", []) or []:
            name = str(item.get("name", "")).replace("models/", "")
            low = name.lower()
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            if not low.startswith("gemini") or "flash" not in low:
                continue
            if any(bad in low for bad in (
                "image", "tts", "audio", "live", "embedding",
                "robotics", "computer", "vision", "exp"
            )):
                continue
            found.append(name)
    except Exception as error:
        logger.warning("No se pudo listar modelos de Gemini: %s", error)

    # Versiones más nuevas primero; los "lite" al final.
    found.sort(reverse=True)
    found.sort(key=lambda n: "lite" in n.lower())
    found = found[:5]
    if found:
        _DISCOVERED_MODELS_CACHE["ts"] = now
        _DISCOVERED_MODELS_CACHE["models"] = found
        logger.info("Modelos Gemini descubiertos: %s", ", ".join(found))
    return found

async def assistant_web_search_context(question):
    """Obtiene contexto web reciente mediante Gemini Search, separado de Gemma."""
    if not GEMINI_WEB_SEARCH or not GEMINI_SEARCH_API_KEY:
        return ""

    today_text = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "systemInstruction": {
            "parts": [{
                "text": (
                    "Eres el motor de investigación web de ApexQuant. "
                    f"La fecha de hoy es {today_text} (UTC). "
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
        import time
        dead = set()  # modelos que dieron 404 (no existen), no se reintentan
        for round_index in range(2):
            if round_index == 0:
                chain = assistant_model_chain(GEMINI_SEARCH_MODEL)
            else:
                # Segunda ronda: pausa corta y se suman los modelos que Google lista hoy.
                time.sleep(2)
                chain = assistant_model_chain(
                    GEMINI_SEARCH_MODEL,
                    assistant_discovered_models(GEMINI_SEARCH_API_KEY)
                )
            for model in chain:
                if model in dead:
                    continue
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent"
                )
                request = Request(
                    url,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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
                        error.code, model, error_body[:300]
                    )
                    if error.code == 404:
                        dead.add(model)
                        continue
                    if error.code in (500, 502, 503, 504):
                        continue
                    return {}
                except Exception as error:
                    logger.warning("Gemini web search falló con %s: %s", model, error)
                    continue
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

    def post_model(model, body_payload, timeout):
        body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
        url = GEMMA_API_URL.format(model=model)
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "x-goog-api-key": GEMMA_API_KEY,
                "Content-Type": "application/json"
            }
        )
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def lean_payload():
        """Versión más ligera de la petición para cuando Gemma devuelve 500."""
        lean = json.loads(json.dumps(payload))
        lean["generationConfig"] = {
            "maxOutputTokens": ASSISTANT_MAX_OUTPUT + ASSISTANT_THINKING_HEADROOM,
            "temperature": 0.8
        }
        lean["contents"] = assistant_gemini_contents((history or [])[-2:], question)
        return lean

    def compact_payload():
        """Última carta contra el 500 de Gemma: petición mínima, sin historial."""
        base = APEXQUANT_ASSISTANT_INSTRUCTIONS
        extra = ""
        if calendar_context:
            extra += "\n\n" + calendar_context[:2500]
        if web_context:
            extra += "\n\nCONTEXTO WEB RECIENTE:\n" + web_context[:2500]
        return {
            "systemInstruction": {"parts": [{"text": base + extra}]},
            "contents": assistant_gemini_contents([], question),
            "generationConfig": {
                "maxOutputTokens": ASSISTANT_MAX_OUTPUT + ASSISTANT_THINKING_HEADROOM
            }
        }

    def request_gemma():
        import time
        last_error = None

        # Intento 1 y 2: Gemma con la petición completa (reintento si es error 5xx/red).
        # Intento 3: Gemma con petición ligera (sin topK/topP, menos historial).
        # Intento 4: Gemma con petición mínima (sin historial).
        attempts = [
            (GEMMA_MODEL, payload, 90),
            (GEMMA_MODEL, payload, 90),
            (GEMMA_MODEL, lean_payload(), 90),
            (GEMMA_MODEL, compact_payload(), 60),
        ]
        for index, (model, body_payload, timeout) in enumerate(attempts, start=1):
            try:
                return post_model(model, body_payload, timeout)
            except HTTPError as error:
                error_body = error.read().decode("utf-8", errors="replace")
                logger.error(
                    "Gemma HTTP %s para modelo %s (intento %s): %s",
                    error.code, model, index, error_body[:1500]
                )
                last_error = RuntimeError(
                    f"Gemma HTTP {error.code} para modelo {model}: {error_body[:500]}"
                )
                # Solo se reintenta en errores temporales del servidor.
                if error.code not in (500, 502, 503, 504):
                    raise last_error from error
                time.sleep(1.5 * index)
            except Exception as error:
                logger.error("Gemma falló (intento %s): %s", index, error)
                last_error = error
                time.sleep(1.5 * index)

        # Último recurso: responder con un modelo Gemini para que el usuario nunca se quede sin respuesta.
        # Ronda 1: modelos configurados. Ronda 2 (tras una pausa): también los modelos
        # que Google lista como disponibles hoy. Los 404 no se reintentan.
        dead = set()
        fatal = False
        for round_index in range(2):
            if fatal:
                break
            if round_index == 0:
                chain = assistant_model_chain(GEMINI_SEARCH_MODEL)
            else:
                time.sleep(3)
                chain = assistant_model_chain(
                    GEMINI_SEARCH_MODEL,
                    assistant_discovered_models(GEMMA_API_KEY)
                )
            for fallback_model in chain:
                if fallback_model in dead:
                    continue
                try:
                    logger.warning("Gemma no respondió; usando respaldo %s", fallback_model)
                    return post_model(fallback_model, compact_payload(), 60)
                except HTTPError as error:
                    error_body = error.read().decode("utf-8", errors="replace")
                    logger.error(
                        "Respaldo %s HTTP %s: %s", fallback_model, error.code, error_body[:300]
                    )
                    if error.code == 404:
                        dead.add(fallback_model)
                        continue
                    if error.code in (401, 403):
                        fatal = True
                        break
                    continue
                except Exception as error:
                    logger.error("Respaldo %s falló: %s", fallback_model, error)
                    continue

        raise last_error or RuntimeError("Gemma HTTP 500: sin respuesta del modelo")

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, request_gemma)
        answer = assistant_extract_output(data)
        if answer:
            answer = assistant_prepare_text(answer)
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

    # Los avisos de error (⚠️) no se guardan en el historial: contaminarían
    # las siguientes consultas con texto que no es una respuesta real.
    if not str(answer).lstrip().startswith("⚠️"):
        history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}
        ])
    context.user_data["assistant_history"] = history[-ASSISTANT_MAX_HISTORY:]

    raw_answer = assistant_truncate(answer, 3900)
    try:
        # Markdown del modelo -> negrita/cursiva reales de Telegram (HTML).
        await update.message.reply_text(
            assistant_markdown_to_html(raw_answer),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=assistant_keyboard()
        )
    except Exception as send_error:
        # Respaldo automático: si Telegram rechaza el formato, se reenvía como
        # texto plano limpio para que el usuario siempre reciba respuesta.
        logger.warning("Formato de la respuesta del asistente rechazado, se reenvía en texto plano: %s", send_error)
        await update.message.reply_text(
            assistant_markdown_to_plain(raw_answer),
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
        if data == "broker_bonus":
            await show_broker_bonus(query)
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
        if data == "calendar_medium":
            await show_calendar_medium(query)
            return
        if data == "calendar_low":
            await show_calendar_low(query)
            return
        if data.startswith("calpage_"):
            await show_calendar_page(query, data.replace("calpage_", "", 1))
            return
        if data.startswith("calendar_context_"):
            event_key = data.replace("calendar_context_", "", 1)
            await show_calendar_context(query, event_key)
            return
        if data.startswith("currency_"):
            await show_currency_events(query, data.replace("currency_", "", 1))
            return
        if data == "copy_terms":
            await show_copy_terms(query, 0)
            return
        if data == "copy_terms_read":
            await show_copy_menu(query)
            return
        if data.startswith("copy_terms_p_"):
            await show_copy_terms(query, data.replace("copy_terms_p_", "", 1))
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
        if data == "admin_broadcast":
            await admin_broadcast_prompt(query, context)
            return
        if data == "admin_broadcast_send":
            await admin_broadcast_send(query, context)
            return
        if data == "admin_broadcast_cancel":
            await admin_broadcast_cancel(query, context)
            return
        if data == "admin_tech":
            await show_admin_tech(query)
            return
        if data == "admin_tech_toggle":
            await admin_tech_toggle(query)
            return
        if data == "admin_tech_scan":
            await admin_tech_scan(query, context)
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
    logger.info("🚨 Monitor de eventos de alto y medio impacto iniciado.")
    application.create_task(tech_alerts_monitor(application), name="apexquant_tech_alerts")
    logger.info("🧭 Monitor de alertas técnicas iniciado (requiere TWELVEDATA_API_KEY).")


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
