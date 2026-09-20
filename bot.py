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
# CONFIGURACIÃ“N
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Falta la variable de entorno BOT_TOKEN")


# ============================================================
# REFERIDOS â€” ALMACENAMIENTO
# ============================================================

# Ruta del archivo de referidos. En hosting (Railway, Render, etc.) apÃºntala
# a un volumen persistente, por ejemplo: REFERRALS_FILE=/data/referrals.json
REFERRALS_FILE = os.getenv("REFERRALS_FILE", "referrals.json")

# ============================================================
# SEÃ‘ALES â€” SUSCRIPCIONES
# ============================================================

SUBSCRIPTIONS_FILE = os.getenv("SUBSCRIPTIONS_FILE", "subscriptions.json")
SIGNALS_PRICE_USDT = 30
SIGNALS_DURATION_DAYS = 30
USDT_BEP20_ADDRESS = os.getenv("USDT_BEP20_ADDRESS", "")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")


def load_referrals():
    """Carga los datos de referidos desde el archivo JSON."""
    try:
        if not os.path.exists(REFERRALS_FILE):
            return {
                "users": {},
                "referrals": {}
            }

        with open(REFERRALS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Formato de referidos invÃ¡lido")

        data.setdefault("users", {})
        data.setdefault("referrals", {})

        return data

    except Exception as error:
        logger.error("Error cargando referidos: %s", error)

        # Si el archivo existe pero estÃ¡ daÃ±ado, se respalda para que
        # el siguiente guardado NO lo sobrescriba con datos vacÃ­os.
        try:
            if os.path.exists(REFERRALS_FILE):
                backup = f"{REFERRALS_FILE}.corrupt"
                os.replace(REFERRALS_FILE, backup)
                logger.error("Archivo daÃ±ado respaldado en %s", backup)
        except Exception as backup_error:
            logger.error("No se pudo respaldar: %s", backup_error)

        return {
            "users": {},
            "referrals": {}
        }


def save_referrals(data):
    """Guarda los datos de referidos en el archivo JSON."""
    try:
        # Escritura atÃ³mica: se escribe en un temporal y luego se reemplaza,
        # asÃ­ un corte a mitad de escritura no deja el JSON a medias.
        temp_file = f"{REFERRALS_FILE}.tmp"

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

        os.replace(temp_file, REFERRALS_FILE)
    except Exception as error:
        logger.error("Error guardando referidos: %s", error)


def register_user(user):
    """Registra un usuario por su Telegram ID."""
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
        data["referrals"].setdefault(user_id, [])

    else:
        # Actualizar datos bÃ¡sicos sin modificar el referente.
        data["users"][user_id]["username"] = user.username or ""
        data["users"][user_id]["first_name"] = user.first_name or ""
        data["referrals"].setdefault(user_id, [])

    save_referrals(data)
    return data


def process_referral(user, start_parameter):
    """
    Procesa un enlace del tipo:
    /start ref_123456789

    Devuelve:
        True  -> referido registrado correctamente
        False -> no se registrÃ³
    """
    if not user or not start_parameter:
        return False

    parameter = str(start_parameter).strip()

    if not parameter.startswith("ref_"):
        return False

    referrer_id = parameter[4:].strip()

    if not referrer_id.isdigit():
        logger.warning("CÃ³digo de referido invÃ¡lido: %s", parameter)
        return False

    user_id = str(user.id)

    # No permitir auto-referencia.
    if referrer_id == user_id:
        logger.info(
            "Auto-referencia bloqueada para Telegram ID %s",
            user_id
        )
        return False

    data = load_referrals()

    # Registrar al usuario que acaba de iniciar.
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "telegram_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "referred_by": None
        }
    else:
        data["users"][user_id]["username"] = user.username or ""
        data["users"][user_id]["first_name"] = user.first_name or ""

    data["referrals"].setdefault(user_id, [])

    # Si el referente no estÃ¡ en el registro (p. ej. el archivo se
    # reiniciÃ³ tras un redeploy), se crea un registro bÃ¡sico en lugar
    # de descartar el referido. Su nombre se completarÃ¡ cuando abra el bot.
    if referrer_id not in data["users"]:
        logger.warning(
            "Referente %s no estaba registrado. Se crea registro bÃ¡sico.",
            referrer_id
        )
        data["users"][referrer_id] = {
            "telegram_id": int(referrer_id),
            "username": "",
            "first_name": "",
            "referred_by": None
        }

    # Una cuenta solamente puede tener un referente.
    if data["users"][user_id].get("referred_by"):
        logger.info(
            "Usuario %s ya tiene referente %s. No se cambia.",
            user_id,
            data["users"][user_id]["referred_by"]
        )
        save_referrals(data)
        return False

    # Evitar duplicados.
    data["referrals"].setdefault(referrer_id, [])

    if user_id in data["referrals"][referrer_id]:
        logger.info(
            "Usuario %s ya estÃ¡ registrado como referido de %s.",
            user_id,
            referrer_id
        )

        data["users"][user_id]["referred_by"] = referrer_id

        save_referrals(data)
        return False

    data["referrals"][referrer_id].append(user_id)
    data["users"][user_id]["referred_by"] = referrer_id

    save_referrals(data)

    logger.info(
        "Nuevo referido registrado: %s -> %s",
        referrer_id,
        user_id
    )

    return True


def get_referral_count(user_id):
    """Devuelve el nÃºmero real de referidos de un usuario."""
    data = load_referrals()

    return len(
        data["referrals"].get(
            str(user_id),
            []
        )
    )


FINANCE_CALENDAR_BASE = (
    "https://www.financecalendar.com/wp-json/fc/v1"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("apex_quant")


# ============================================================
# TECLADO PRINCIPAL
# ============================================================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ“Š Mercados",
                callback_data="markets",
            ),
            InlineKeyboardButton(
                "ðŸ“¡ SeÃ±ales",
                callback_data="signals",
            ),
        ],
        [
            InlineKeyboardButton(
                "ðŸ’° Planes",
                callback_data="plans",
            ),
            InlineKeyboardButton(
                "ðŸ‘¥ Referidos",
                callback_data="referrals",
            ),
        ],
        [
            InlineKeyboardButton(
                "ðŸŒ Idioma",
                callback_data="language",
            ),
            InlineKeyboardButton(
                "âš™ï¸ ConfiguraciÃ³n",
                callback_data="settings",
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# MENÃš MERCADOS
# ============================================================

def markets_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ“… Calendario econÃ³mico",
                callback_data="calendar",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸš¨ Noticias alto impacto",
                callback_data="high_news",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ’± Noticias por divisa",
                callback_data="currency_news",
            )
        ],
        [
            InlineKeyboardButton(
                "âš ï¸ Riesgo de noticias",
                callback_data="news_risk",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ“ˆ AnÃ¡lisis diario",
                callback_data="daily_analysis",
            )
        ],
        [
            InlineKeyboardButton(
                "â¬…ï¸ MenÃº principal",
                callback_data="main_menu",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# MENÃš CALENDARIO
# ============================================================

def calendar_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ“… Hoy",
                callback_data="calendar_today",
            ),
            InlineKeyboardButton(
                "ðŸ“… MaÃ±ana",
                callback_data="calendar_tomorrow",
            ),
        ],
        [
            InlineKeyboardButton(
                "ðŸ—“ï¸ Esta semana",
                callback_data="calendar_week",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸš¨ Alto impacto",
                callback_data="calendar_high",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ’± Por divisa",
                callback_data="calendar_currency",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ”„ Actualizar",
                callback_data="calendar_refresh",
            )
        ],
        [
            InlineKeyboardButton(
                "â¬…ï¸ Mercados",
                callback_data="markets",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# MENÃš DIVISAS
# ============================================================

def currency_menu():
    currencies = [
        ("ðŸ‡ºðŸ‡¸ USD", "USD"),
        ("ðŸ‡ªðŸ‡º EUR", "EUR"),
        ("ðŸ‡¬ðŸ‡§ GBP", "GBP"),
        ("ðŸ‡¯ðŸ‡µ JPY", "JPY"),
        ("ðŸ‡¨ðŸ‡­ CHF", "CHF"),
        ("ðŸ‡¨ðŸ‡¦ CAD", "CAD"),
        ("ðŸ‡¦ðŸ‡º AUD", "AUD"),
        ("ðŸ‡³ðŸ‡¿ NZD", "NZD"),
    ]

    keyboard = []

    for i in range(0, len(currencies), 2):
        row = []

        for name, code in currencies[i:i + 2]:
            row.append(
                InlineKeyboardButton(
                    name,
                    callback_data=f"currency_{code}",
                )
            )

        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                "â¬…ï¸ Calendario",
                callback_data="calendar",
            )
        ]
    )

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# BOTÃ“N MENÃš PRINCIPAL
# ============================================================

def back_main_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "â¬…ï¸ MenÃº principal",
                    callback_data="main_menu",
                )
            ]
        ]
    )


# ============================================================
# SUSCRIPCIONES DE SEÃ‘ALES â€” ALMACENAMIENTO
# ============================================================

def load_subscriptions():
    """Carga las suscripciones desde un archivo JSON."""
    try:
        if not os.path.exists(SUBSCRIPTIONS_FILE):
            return {}

        with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception as error:
        logger.error("Error cargando suscripciones: %s", error)
        return {}


def save_subscriptions(data):
    """Guarda las suscripciones de forma atÃ³mica."""
    try:
        temp_file = f"{SUBSCRIPTIONS_FILE}.tmp"

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

        os.replace(temp_file, SUBSCRIPTIONS_FILE)

    except Exception as error:
        logger.error("Error guardando suscripciones: %s", error)


def get_subscription(user_id):
    """Devuelve la suscripciÃ³n de un usuario, si existe."""
    data = load_subscriptions()
    return data.get(str(user_id))


def activate_subscription(user_id):
    """Activa o renueva una suscripciÃ³n por 30 dÃ­as."""
    now = datetime.now()
    current = get_subscription(user_id)

    if current:
        try:
            current_expiry = datetime.fromisoformat(
                current.get("expires_at", "")
            )
        except (TypeError, ValueError):
            current_expiry = now

        start_date = current_expiry if current_expiry > now else now
    else:
        start_date = now

    expires_at = start_date + timedelta(days=SIGNALS_DURATION_DAYS)

    data = load_subscriptions()
    data[str(user_id)] = {
        "telegram_id": int(user_id),
        "status": "active",
        "started_at": start_date.isoformat(),
        "expires_at": expires_at.isoformat(),
        "price_usdt": SIGNALS_PRICE_USDT,
        "payment_network": "BEP20",
    }
    save_subscriptions(data)

    return data[str(user_id)]


def subscription_is_active(user_id):
    """Comprueba si una suscripciÃ³n estÃ¡ activa y no vencida."""
    subscription = get_subscription(user_id)

    if not subscription or subscription.get("status") != "active":
        return False

    try:
        expires_at = datetime.fromisoformat(subscription["expires_at"])
    except (KeyError, TypeError, ValueError):
        return False

    if expires_at <= datetime.now():
        data = load_subscriptions()
        data[str(user_id)]["status"] = "expired"
        save_subscriptions(data)
        return False

    return True


def subscription_status_text(user_id):
    """Genera el estado de la suscripciÃ³n para mostrar al usuario."""
    subscription = get_subscription(user_id)

    if not subscription or not subscription_is_active(user_id):
        return (
            "ðŸ”´ *SuscripciÃ³n no activa*\n\n"
            f"Acceso a seÃ±ales: *${SIGNALS_PRICE_USDT} USDT/mes*\n"
            "Red de pago: *BEP20*"
        )

    try:
        expires_at = datetime.fromisoformat(subscription["expires_at"])
        remaining = max(
            0,
            (expires_at.date() - datetime.now().date()).days
        )
        expiry_text = expires_at.strftime("%d/%m/%Y")
    except (KeyError, TypeError, ValueError):
        remaining = 0
        expiry_text = "No disponible"

    return (
        "ðŸŸ¢ *SuscripciÃ³n activa*\n\n"
        f"ðŸ“… Vencimiento: *{expiry_text}*\n"
        f"â³ DÃ­as restantes: *{remaining}*\n"
        f"ðŸ’µ Precio: *${SIGNALS_PRICE_USDT} USDT/mes*\n"
        "ðŸŒ Red: *BEP20*"
    )


def is_admin(user_id):
    """Comprueba si el Telegram ID pertenece al administrador configurado."""
    return bool(
        ADMIN_TELEGRAM_ID
        and str(user_id) == str(ADMIN_TELEGRAM_ID)
    )


# ============================================================
# FINANCE CALENDAR â€” PETICIÃ“N HTTP
# ============================================================

def fetch_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": "ApexQuant/1.0"
        },
    )

    with urlopen(request, timeout=15) as response:
        data = response.read().decode("utf-8")

    return json.loads(data)


async def finance_request(endpoint, params=None):
    url = f"{FINANCE_CALENDAR_BASE}/{endpoint}"

    if params:
        url += "?" + urlencode(params)

    try:
        data = await asyncio.to_thread(
            fetch_json,
            url,
        )

        return data

    except Exception as error:
        logger.error(
            "FinanceCalendar error: %s",
            error,
        )

        return None


# ============================================================
# FECHAS
# ============================================================

def today_date():
    return date.today()


def tomorrow_date():
    return date.today() + timedelta(days=1)


def week_dates():
    today = date.today()

    monday = today - timedelta(
        days=today.weekday()
    )

    sunday = monday + timedelta(days=6)

    return monday, sunday# ============================================================
# FORMATO IMPACTO
# ============================================================

def impact_label(impact):
    impact = str(impact or "").lower()

    if impact == "high":
        return "ðŸ”´ ALTO"

    if impact == "medium":
        return "ðŸŸ  MEDIO"

    if impact == "low":
        return "ðŸŸ¢ BAJO"

    return "âšª SIN CLASIFICAR"


# ============================================================
# FORMATO DE EVENTOS
# ============================================================

def format_event(event):
    event_date = event.get("date", "")
    time_et = event.get("time_et", "")
    title = event.get("title") or event.get(
        "name",
        "Evento econÃ³mico",
    )

    impact = event.get("impact")
    category = event.get("category")
    consensus = event.get("consensus")
    prior = event.get("prior")
    actual = event.get("actual")
    url = event.get("url")

    lines = []

    if time_et:
        lines.append(
            f"ðŸ• {time_et} ET"
        )
    else:
        lines.append(
            "ðŸ• Hora no disponible"
        )

    lines.append(
        f"ðŸ“Œ {title}"
    )

    lines.append(
        f"ðŸ“Š Impacto: {impact_label(impact)}"
    )

    if category:
        lines.append(
            f"ðŸ“‚ {category}"
        )

    if consensus:
        lines.append(
            f"ðŸ”® Consenso: {consensus}"
        )

    if prior:
        lines.append(
            f"â—€ï¸ Anterior: {prior}"
        )

    if actual:
        lines.append(
            f"âœ… Actual: {actual}"
        )

    if url:
        lines.append(
            f"ðŸ”— {url}"
        )

    return "\n".join(lines)


# ============================================================
# OBTENER EVENTOS POR RANGO
# ============================================================

async def get_calendar_events(
    start_date,
    end_date,
    impact=None,
):
    params = {
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "limit": "500",
    }

    if impact:
        params["impact"] = impact

    data = await finance_request(
        "calendar",
        params,
    )

    if not data:
        return []

    if isinstance(data, dict):
        events = data.get("events", [])

        if isinstance(events, list):
            return events

    if isinstance(data, list):
        return data

    return []


# ============================================================
# MOSTRAR LISTA DE EVENTOS
# ============================================================

async def show_events(
    query,
    title,
    start_date,
    end_date,
    impact=None,
):
    events = await get_calendar_events(
        start_date,
        end_date,
        impact,
    )

    if not events:
        text = (
            f"ðŸ“… *{title}*\n\n"
            "No se encontraron eventos econÃ³micos "
            "para el periodo seleccionado.\n\n"
            "ðŸ”„ Puedes actualizar el calendario."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

        return

    lines = [
        f"ðŸ“… *{title}*",
        "",
    ]

    current_date = None

    for event in events:
        event_date = event.get("date")

        if event_date != current_date:
            current_date = event_date

            lines.append(
                f"ðŸ“† *{event_date}*"
            )

            lines.append("")

        lines.append(
            format_event(event)
        )

        lines.append(
            "â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€"
        )

    lines.extend(
        [
            "",
            "âš ï¸ Los eventos econÃ³micos pueden "
            "provocar movimientos rÃ¡pidos y "
            "significativos en los mercados.",
            "",
            "ðŸ”— Fuente: FinanceCalendar.com",
        ]
    )

    text = "\n".join(lines)

    # Telegram tiene un lÃ­mite de longitud por mensaje.
    # Si hay demasiados eventos, mostramos los primeros.
    if len(text) > 3900:
        text = text[:3800]
        text += (
            "\n\nâ€¦ Lista recortada por lÃ­mite de mensaje."
            "\nðŸ”— Fuente: FinanceCalendar.com"
        )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


# ============================================================
# ACTIVACIÃ“N MANUAL DE SUSCRIPCIONES
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
                "â›” No tienes permiso para utilizar este comando."
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
            "âŒ El Telegram ID debe ser numÃ©rico."
        )
        return

    subscription = activate_subscription(int(target_id))
    expires_at = datetime.fromisoformat(
        subscription["expires_at"]
    ).strftime("%d/%m/%Y")

    await update.message.reply_text(
        "âœ… *SuscripciÃ³n activada*\n\n"
        f"ðŸ†” Telegram ID: `{target_id}`\n"
        f"ðŸ’µ Plan: *${SIGNALS_PRICE_USDT} USDT / 30 dÃ­as*\n"
        "ðŸŒ Red: *BEP20*\n"
        f"ðŸ“… Vencimiento: *{expires_at}*",
        parse_mode="Markdown",
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    logger.info(
        "/start de %s con args=%s",
        user.id if user else None,
        context.args,
    )

    if user:
        register_user(user)

    referral_registered = False

    if context.args and user:
        referral_registered = process_referral(
            user,
            context.args[0],
        )

    text = (
        "ðŸ”¥ *Bienvenido a Apex Quant*\n\n"
        "Tu centro de informaciÃ³n y herramientas "
        "para mercados financieros.\n\n"
        "ðŸ“Š Mercados\n"
        "ðŸ“¡ SeÃ±ales\n"
        "ðŸ’° Planes\n"
        "ðŸ‘¥ Referidos\n"
        "ðŸŒ Idioma\n"
        "âš™ï¸ ConfiguraciÃ³n\n\n"
        "Selecciona una opciÃ³n para comenzar.\n\n"
        "âš ï¸ *Aviso de riesgo:* la informaciÃ³n, "
        "anÃ¡lisis y seÃ±ales no garantizan resultados. "
        "Los mercados financieros implican riesgo "
        "y pueden producir pÃ©rdidas."
    )

    if referral_registered:
        text += (
            "\n\n"
            "ðŸŽ‰ *Â¡Referido registrado correctamente!*\n"
            "Gracias por unirte a Apex Quant mediante "
            "un enlace de invitaciÃ³n."
        )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )


# ============================================================
# MERCADOS
# ============================================================

async def show_markets(query):
    text = (
        "ðŸ“Š *Mercados*\n\n"
        "Consulta informaciÃ³n y anÃ¡lisis relacionados "
        "con los mercados financieros.\n\n"
        "Selecciona una opciÃ³n:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=markets_menu(),
    )


# ============================================================
# CALENDARIO
# ============================================================

async def show_calendar(query):
    text = (
        "ðŸ“… *Calendario econÃ³mico*\n\n"
        "Consulta eventos econÃ³micos que pueden "
        "generar volatilidad en los mercados.\n\n"
        "Selecciona el periodo que deseas consultar.\n\n"
        "ðŸ”— Datos: FinanceCalendar.com"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


# ============================================================
# NOTICIAS ALTO IMPACTO
# ============================================================

async def show_high_news(query):
    today = today_date()
    end_date = today + timedelta(days=7)

    await show_events(
        query,
        "Noticias de alto impacto",
        today,
        end_date,
        impact="high",
    )


# ============================================================
# RIESGO DE NOTICIAS
# ============================================================

async def show_news_risk(query):
    today = today_date()
    end_date = today + timedelta(days=1)

    events = await get_calendar_events(
        today,
        end_date,
        impact="high",
    )

    if events:
        text = (
            "âš ï¸ *Riesgo de noticias*\n\n"
            "Se detectaron eventos de *alto impacto* "
            "en el periodo actual.\n\n"
            "Antes de ejecutar una operaciÃ³n, "
            "revisa especialmente estos eventos.\n\n"
        )

        for event in events[:8]:
            title = event.get(
                "title",
                event.get(
                    "name",
                    "Evento",
                ),
            )

            time_et = event.get(
                "time_et",
                "hora no disponible",
            )

            text += (
                f"ðŸ”´ {time_et} ET â€” {title}\n"
            )

        text += (
            "\nâš ï¸ Una noticia puede provocar "
            "volatilidad, spread elevado y "
            "movimientos bruscos.\n\n"
            "ðŸ”— Fuente: FinanceCalendar.com"
        )

    else:
        text = (
            "âš ï¸ *Riesgo de noticias*\n\n"
            "No se encontraron eventos de alto impacto "
            "para el periodo consultado.\n\n"
            "Esto no elimina el riesgo de mercado.\n\n"
            "ðŸ”— Fuente: FinanceCalendar.com"
        )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# NOTICIAS POR DIVISA
# ============================================================

async def show_currency_news(query):
    text = (
        "ðŸ’± *Noticias por divisa*\n\n"
        "Selecciona la moneda que deseas analizar:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=currency_menu(),
    )


# ============================================================
# FILTRO POR DIVISA
# ============================================================

CURRENCY_KEYWORDS = {
    "USD": [
        "united states",
        "us ",
        "u.s.",
        "federal reserve",
        "fed ",
        "dollar",
        "usd",
        "american",
    ],
    "EUR": [
        "euro",
        "eurozone",
        "euro area",
        "european central bank",
        "ecb",
        "eur",
        "germany",
        "france",
        "italy",
        "spain",
    ],
    "GBP": [
        "united kingdom",
        "uk ",
        "britain",
        "british",
        "bank of england",
        "boe",
        "pound",
        "gbp",
    ],
    "JPY": [
        "japan",
        "japanese",
        "bank of japan",
        "boj",
        "yen",
        "jpy",
    ],
    "CHF": [
        "switzerland",
        "swiss",
        "swiss national bank",
        "snb",
        "franc",
        "chf",
    ],
    "CAD": [
        "canada",
        "canadian",
        "bank of canada",
        "boc",
        "cad",
    ],
    "AUD": [
        "australia",
        "australian",
        "reserve bank of australia",
        "rba",
        "aud",
    ],
    "NZD": [
        "new zealand",
        "new zealand dollar",
        "reserve bank of new zealand",
        "rbnz",
        "nzd",
    ],
}


def event_matches_currency(event, currency):
    keywords = CURRENCY_KEYWORDS.get(
        currency,
        [],
    )

    currency_fields = [
        event.get("currency"),
        event.get("currency_code"),
        event.get("curr"),
        event.get("ccy"),
    ]

    for value in currency_fields:
        if value:
            if str(value).upper() == currency.upper():
                return True

    searchable = " ".join(
        [
            str(event.get("name", "")),
            str(event.get("title", "")),
            str(event.get("category", "")),
        ]
    ).lower()

    for keyword in keywords:
        if keyword.lower() in searchable:
            return True

    return False# ============================================================
# EVENTOS POR DIVISA
# ============================================================

async def currency_events(
    query,
    currency,
):
    today = today_date()
    end_date = today + timedelta(days=7)

    events = await get_calendar_events(
        today,
        end_date,
    )

    filtered = [
        event
        for event in events
        if event_matches_currency(
            event,
            currency,
        )
    ]

    if not filtered:
        text = (
            f"ðŸ’± *Noticias {currency}*\n\n"
            "No se encontraron eventos relacionados "
            f"con {currency} durante los prÃ³ximos dÃ­as.\n\n"
            "ðŸ”— Fuente: FinanceCalendar.com"
        )

    else:
        lines = [
            f"ðŸ’± *Noticias {currency}*",
            "",
        ]

        for event in filtered[:12]:
            event_date = event.get(
                "date",
                "",
            )

            title = event.get(
                "title",
                event.get(
                    "name",
                    "Evento",
                ),
            )

            time_et = event.get(
                "time_et",
                "hora no disponible",
            )

            impact = impact_label(
                event.get("impact")
            )

            lines.append(
                f"ðŸ“† {event_date}"
            )

            lines.append(
                f"ðŸ• {time_et} ET"
            )

            lines.append(
                f"ðŸ“Œ {title}"
            )

            lines.append(
                f"ðŸ“Š {impact}"
            )

            consensus = event.get("consensus")

            if consensus:
                lines.append(
                    f"ðŸ”® Consenso: {consensus}"
                )

            prior = event.get("prior")

            if prior:
                lines.append(
                    f"â—€ï¸ Anterior: {prior}"
                )

            lines.append(
                "â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€"
            )

        lines.append(
            "ðŸ”— Fuente: FinanceCalendar.com"
        )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=currency_menu(),
    )


# ============================================================
# ANÃLISIS DIARIO
# ============================================================

async def show_daily_analysis(query):
    text = (
        "ðŸ“ˆ *AnÃ¡lisis diario Apex Quant*\n\n"
        "La metodologÃ­a de anÃ¡lisis contempla:\n\n"
        "ðŸ”¹ BOS â€” Break of Structure\n"
        "ðŸ”¹ FVG â€” Fair Value Gap\n"
        "ðŸ”¹ Liquidez\n"
        "ðŸ”¹ Volumen\n"
        "ðŸ”¹ RSI 14\n"
        "ðŸ”¹ HH / HL\n"
        "ðŸ”¹ Estructura de mercado\n\n"
        "ðŸŽ¯ Instrumentos principales:\n"
        "â€¢ EUR/USD\n"
        "â€¢ GBP/USD\n"
        "â€¢ GBP/JPY\n\n"
        "â±ï¸ *Marcos de anÃ¡lisis:*\n"
        "â€¢ H4 â€” DirecciÃ³n\n"
        "â€¢ H1 â€” Liquidez y estructura\n"
        "â€¢ M5 â€” Entrada\n\n"
        "âš ï¸ El anÃ¡lisis es informativo. "
        "Ninguna configuraciÃ³n tÃ©cnica garantiza "
        "una operaciÃ³n ganadora."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# SEÃ‘ALES
# ============================================================

async def show_signals(query):
    text = (
        "ðŸ“¡ *SeÃ±ales Apex Quant*\n\n"
        "Accede a las seÃ±ales de trading de Apex Quant "
        "mediante una suscripciÃ³n mensual.\n\n"
        f"ðŸ’µ *Precio: ${SIGNALS_PRICE_USDT} USDT / mes*\n"
        "ðŸŒ *Red de pago: USDT BEP20*\n\n"
        "La suscripciÃ³n te permitirÃ¡ recibir las seÃ±ales "
        "publicadas por Apex Quant durante el periodo activo.\n\n"
        "âš ï¸ *Aviso de riesgo:* las seÃ±ales son informaciÃ³n "
        "y anÃ¡lisis de mercado. No garantizan ganancias. "
        "El trading implica riesgo y puede producir pÃ©rdidas."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ’³ Suscribirme â€” $30",
                callback_data="signal_subscribe",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ“‹ CÃ³mo pagar",
                callback_data="signal_payment",
            ),
            InlineKeyboardButton(
                "ðŸ“… Mi suscripciÃ³n",
                callback_data="signal_status",
            ),
        ],
        [
            InlineKeyboardButton(
                "â¬…ï¸ MenÃº principal",
                callback_data="main_menu",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_signal_subscription(query):
    text = (
        "ðŸ’³ *SuscripciÃ³n de SeÃ±ales Apex Quant*\n\n"
        f"ðŸ’µ Precio: *${SIGNALS_PRICE_USDT} USDT*\n"
        "ðŸ“† DuraciÃ³n: *30 dÃ­as*\n"
        "ðŸŒ Red: *BEP20*\n\n"
        "El pago se realizarÃ¡ manualmente mediante "
        "USDT en la red BEP20.\n\n"
        "DespuÃ©s de realizar el pago, conserva el "
        "comprobante o TXID para enviarlo al administrador "
        "y solicitar la activaciÃ³n de tu suscripciÃ³n.\n\n"
        "âš ï¸ La suscripciÃ³n da acceso a seÃ±ales, pero "
        "no garantiza resultados ni ganancias."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ“‹ Instrucciones de pago",
                callback_data="signal_payment",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ“… Consultar mi suscripciÃ³n",
                callback_data="signal_status",
            )
        ],
        [
            InlineKeyboardButton(
                "â¬…ï¸ SeÃ±ales",
                callback_data="signals",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_signal_payment(query):
    if USDT_BEP20_ADDRESS:
        wallet_text = (
            "ðŸ’³ *DirecciÃ³n USDT BEP20:*\n"
            f"`{USDT_BEP20_ADDRESS}`"
        )
    else:
        wallet_text = (
            "ðŸ’³ *DirecciÃ³n de pago:*\n"
            "La direcciÃ³n USDT BEP20 serÃ¡ configurada "
            "por el administrador antes de aceptar pagos."
        )

    text = (
        "ðŸ“‹ *Instrucciones de pago*\n\n"
        f"1ï¸âƒ£ EnvÃ­a *${SIGNALS_PRICE_USDT} USDT*.\n"
        "2ï¸âƒ£ Utiliza Ãºnicamente la red *BEP20*.\n"
        "3ï¸âƒ£ Conserva el comprobante y/o TXID.\n"
        "4ï¸âƒ£ EnvÃ­a el comprobante al administrador "
        "para verificar el pago.\n"
        "5ï¸âƒ£ Una vez verificado, tu suscripciÃ³n serÃ¡ "
        "activada manualmente por 30 dÃ­as.\n\n"
        f"{wallet_text}\n\n"
        "âš ï¸ *IMPORTANTE:* enviar USDT por una red distinta "
        "de BEP20 puede provocar la pÃ©rdida de los fondos.\n\n"
        "âš ï¸ Apex Quant no garantiza ganancias. "
        "Las operaciones de trading implican riesgo."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ“… Mi suscripciÃ³n",
                callback_data="signal_status",
            )
        ],
        [
            InlineKeyboardButton(
                "â¬…ï¸ SeÃ±ales",
                callback_data="signals",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_signal_status(query):
    text = (
        "ðŸ“… *Mi suscripciÃ³n de seÃ±ales*\n\n"
        f"{subscription_status_text(query.from_user.id)}\n\n"
        "La activaciÃ³n y renovaciÃ³n se realizan "
        "manualmente despuÃ©s de verificar el pago."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ’³ Suscribirme / Renovar",
                callback_data="signal_subscribe",
            )
        ],
        [
            InlineKeyboardButton(
                "â¬…ï¸ SeÃ±ales",
                callback_data="signals",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )



# ============================================================
# PLANES
# ============================================================

async def show_plans(query):
    text = (
        "ðŸ’° *Planes Apex Quant*\n\n"
        "Los siguientes porcentajes representan "
        "estimaciones de referencia y NO son "
        "rendimientos garantizados.\n\n"
        "ðŸŸ¢ *30 dÃ­as*\n"
        "EstimaciÃ³n: *8%*\n\n"
        "ðŸŸ¢ *90 dÃ­as*\n"
        "EstimaciÃ³n: *24%*\n\n"
        "ðŸŸ¢ *180 dÃ­as*\n"
        "EstimaciÃ³n: *48%*\n\n"
        "ðŸŸ¢ *360 dÃ­as*\n"
        "EstimaciÃ³n: *96%*\n\n"
        "âš ï¸ Los resultados pueden variar segÃºn "
        "las condiciones del mercado y existe "
        "posibilidad de pÃ©rdidas.\n\n"
        "ðŸ“Œ Los porcentajes mostrados son Ãºnicamente "
        "estimaciones y no representan una promesa "
        "de rendimiento."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# REFERIDOS
# ============================================================

async def show_referrals(query, context):
    user = query.from_user

    register_user(user)

    telegram_id = user.id

    # Se usa el username real del bot conectado al token, para que el
    # enlace nunca apunte a otro bot por un nombre escrito a mano.
    bot_username = context.bot.username or "ApexQuantFXBot"

    invite_link = (
        f"https://t.me/{bot_username}"
        f"?start=ref_{telegram_id}"
    )

    referral_count = get_referral_count(
        telegram_id
    )

    text = (
        "ðŸ‘¥ *Programa de Referidos Apex Quant*\n\n"
        "Invita a otras personas a conocer "
        "Apex Quant utilizando tu enlace personal.\n\n"
        "ðŸ”— *Tu enlace personal:*\n"
        f"`{invite_link}`\n\n"
        "ðŸ†” *Tu Telegram ID:*\n"
        f"`{telegram_id}`\n\n"
        f"ðŸ‘¥ *Referidos registrados:* "
        f"*{referral_count}*\n\n"
        "ðŸ“Œ Cada persona debe entrar mediante "
        "tu enlace y pulsar *START* para que "
        "el sistema pueda registrar la invitaciÃ³n.\n\n"
        "ðŸ›¡ï¸ El sistema utiliza el ID Ãºnico de "
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
        "ðŸŒ *Idioma*\n\n"
        "Selecciona el idioma del bot:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ‡ªðŸ‡¸ EspaÃ±ol",
                callback_data="language_es",
            ),
            InlineKeyboardButton(
                "ðŸ‡ºðŸ‡¸ English",
                callback_data="language_en",
            ),
        ],
        [
            InlineKeyboardButton(
                "â¬…ï¸ MenÃº principal",
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
# CONFIGURACIÃ“N
# ============================================================

async def show_settings(query):
    text = (
        "âš™ï¸ *ConfiguraciÃ³n*\n\n"
        "La secciÃ³n de configuraciÃ³n se encuentra "
        "en preparaciÃ³n.\n\n"
        "PrÃ³ximamente podrÃ¡s gestionar preferencias "
        "de idioma, notificaciones y otras opciones."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# CALENDARIO â€” HOY
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
# CALENDARIO â€” MAÃ‘ANA
# ============================================================

async def calendar_tomorrow(query):
    tomorrow = tomorrow_date()

    await show_events(
        query,
        "Calendario de maÃ±ana",
        tomorrow,
        tomorrow,
    )


# ============================================================
# CALENDARIO â€” ESTA SEMANA
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
# CALENDARIO â€” ALTO IMPACTO
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
# CALENDARIO â€” POR DIVISA
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
    )# ============================================================
# MANEJADOR PRINCIPAL DE BOTONES
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer()

    data = query.data

    if data == "main_menu":
        text = (
            "ðŸ”¥ *Apex Quant*\n\n"
            "Selecciona una opciÃ³n:"
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    if data == "markets":
        await show_markets(query)
        return

    if data == "signals":
        await show_signals(query)
        return

    if data == "signal_subscribe":
        await show_signal_subscription(query)
        return

    if data == "signal_payment":
        await show_signal_payment(query)
        return

    if data == "signal_status":
        await show_signal_status(query)
        return

    if data == "plans":
        await show_plans(query)
        return

    if data == "referrals":
        await show_referrals(query, context)
        return

    if data == "language":
        await show_language(query)
        return

    if data == "settings":
        await show_settings(query)
        return

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

    if data == "language_es":
        text = (
            "ðŸ‡ªðŸ‡¸ *EspaÃ±ol seleccionado*\n\n"
            "El idioma espaÃ±ol estÃ¡ seleccionado."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )

        return

    if data == "language_en":
        text = (
            "ðŸ‡ºðŸ‡¸ *English selected*\n\n"
            "English is currently selected."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )

        return

    text = (
        "âš ï¸ OpciÃ³n no disponible actualmente."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# CONFIGURACIÃ“N DE LA APLICACIÃ“N
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
# EJECUCIÃ“N
# ============================================================

if __name__ == "__main__":
    main()
