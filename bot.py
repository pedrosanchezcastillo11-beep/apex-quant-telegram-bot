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
                "💰 Planes",
                callback_data="plans",
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

    return InlineKeyboardMarkup(keyboard)


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

    return InlineKeyboardMarkup(keyboard)


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

    return InlineKeyboardMarkup(keyboard)


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
                "⬅️ Calendario",
                callback_data="calendar",
            )
        ]
    )

    return InlineKeyboardMarkup(keyboard)


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
# FINANCE CALENDAR — PETICIÓN HTTP
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

    return monday, sunday


# ============================================================
# FORMATO IMPACTO
# ============================================================

def impact_label(impact):
    impact = str(impact or "").lower()

    if impact == "high":
        return "🔴 ALTO"

    if impact == "medium":
        return "🟠 MEDIO"

    if impact == "low":
        return "🟢 BAJO"

    return "⚪ SIN CLASIFICAR"


# ============================================================
# FORMATO DE EVENTOS
# ============================================================

def format_event(event):
    event_date = event.get("date", "")
    time_et = event.get("time_et", "")
    title = event.get("title") or event.get(
        "name",
        "Evento económico",
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
            f"🕐 {time_et} ET"
        )
    else:
        lines.append(
            "🕐 Hora no disponible"
        )

    lines.append(
        f"📌 {title}"
    )

    lines.append(
        f"📊 Impacto: {impact_label(impact)}"
    )

    if category:
        lines.append(
            f"📂 {category}"
        )

    if consensus:
        lines.append(
            f"🔮 Consenso: {consensus}"
        )

    if prior:
        lines.append(
            f"◀️ Anterior: {prior}"
        )

    if actual:
        lines.append(
            f"✅ Actual: {actual}"
        )

    if url:
        lines.append(
            f"🔗 {url}"
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
            f"📅 *{title}*\n\n"
            "No se encontraron eventos económicos "
            "para el periodo seleccionado.\n\n"
            "🔄 Puedes actualizar el calendario."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

        return

    lines = [
        f"📅 *{title}*",
        "",
    ]

    current_date = None

    for event in events:
        event_date = event.get("date")

        if event_date != current_date:
            current_date = event_date

            lines.append(
                f"📆 *{event_date}*"
            )

            lines.append("")

        lines.append(
            format_event(event)
        )

        lines.append(
            "──────────────"
        )

    lines.extend(
        [
            "",
            "⚠️ Los eventos económicos pueden "
            "provocar movimientos rápidos y "
            "significativos en los mercados.",
            "",
            "🔗 Fuente: FinanceCalendar.com",
        ]
    )

    text = "\n".join(lines)

    # Telegram tiene un límite de longitud por mensaje.
    # Si hay demasiados eventos, mostramos los primeros.
    if len(text) > 3900:
        text = text[:3800]
        text += (
            "\n\n… Lista recortada por límite de mensaje."
            "\n🔗 Fuente: FinanceCalendar.com"
        )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        "🔥 *Bienvenido a Apex Quant*\n\n"
        "Tu centro de información y herramientas "
        "para mercados financieros.\n\n"
        "📊 Mercados\n"
        "📡 Señales\n"
        "💰 Planes\n"
        "👥 Referidos\n"
        "🌐 Idioma\n"
        "⚙️ Configuración\n\n"
        "Selecciona una opción para comenzar.\n\n"
        "⚠️ *Aviso de riesgo:* la información, "
        "análisis y señales no garantizan resultados. "
        "Los mercados financieros implican riesgo "
        "y pueden producir pérdidas."
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
        "📊 *Mercados*\n\n"
        "Consulta información y análisis relacionados "
        "con los mercados financieros.\n\n"
        "Selecciona una opción:"
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
        "📅 *Calendario económico*\n\n"
        "Consulta eventos económicos que pueden "
        "generar volatilidad en los mercados.\n\n"
        "Selecciona el periodo que deseas consultar.\n\n"
        "🔗 Datos: FinanceCalendar.com"
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
            "⚠️ *Riesgo de noticias*\n\n"
            "Se detectaron eventos de *alto impacto* "
            "en el periodo actual.\n\n"
            "Antes de ejecutar una operación, "
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
                f"🔴 {time_et} ET — {title}\n"
            )

        text += (
            "\n⚠️ Una noticia puede provocar "
            "volatilidad, spread elevado y "
            "movimientos bruscos.\n\n"
            "🔗 Fuente: FinanceCalendar.com"
        )

    else:
        text = (
            "⚠️ *Riesgo de noticias*\n\n"
            "No se encontraron eventos de alto impacto "
            "para el periodo consultado.\n\n"
            "Esto no elimina el riesgo de mercado.\n\n"
            "🔗 Fuente: FinanceCalendar.com"
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
        "💱 *Noticias por divisa*\n\n"
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

    # Comprobar primero posibles campos de moneda
    # que pueda devolver la API.
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

    # Mantener el filtro actual por país,
    # institución y descripción del evento.
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

    return False



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
            f"💱 *Noticias {currency}*\n\n"
            "No se encontraron eventos relacionados "
            f"con {currency} durante los próximos días.\n\n"
            "🔗 Fuente: FinanceCalendar.com"
        )

    else:
        lines = [
            f"💱 *Noticias {currency}*",
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
                f"📆 {event_date}"
            )

            lines.append(
                f"🕐 {time_et} ET"
            )

            lines.append(
                f"📌 {title}"
            )

            lines.append(
                f"📊 {impact}"
            )

            consensus = event.get("consensus")

            if consensus:
                lines.append(
                    f"🔮 Consenso: {consensus}"
                )

            prior = event.get("prior")

            if prior:
                lines.append(
                    f"◀️ Anterior: {prior}"
                )

            lines.append(
                "──────────────"
            )

        lines.append(
            "🔗 Fuente: FinanceCalendar.com"
        )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=currency_menu(),
    )


# ============================================================
# ANÁLISIS DIARIO
# ============================================================

async def show_daily_analysis(query):
    text = (
        "📈 *Análisis diario Apex Quant*\n\n"
        "La metodología de análisis contempla:\n\n"
        "🔹 BOS — Break of Structure\n"
        "🔹 FVG — Fair Value Gap\n"
        "🔹 Liquidez\n"
        "🔹 Volumen\n"
        "🔹 RSI 14\n"
        "🔹 HH / HL\n"
        "🔹 Estructura de mercado\n\n"
        "🎯 Instrumentos principales:\n"
        "• EUR/USD\n"
        "• GBP/USD\n"
        "• GBP/JPY\n\n"
        "⏱️ *Marcos de análisis:*\n"
        "• H4 — Dirección\n"
        "• H1 — Liquidez y estructura\n"
        "• M5 — Entrada\n\n"
        "⚠️ El análisis es informativo. "
        "Ninguna configuración técnica garantiza "
        "una operación ganadora."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# SEÑALES
# ============================================================

async def show_signals(query):
    text = (
        "📡 *Señales Apex Quant*\n\n"
        "Cuando exista una oportunidad que cumpla "
        "los criterios establecidos, la señal podrá incluir:\n\n"
        "💱 Par\n"
        "📈 Dirección\n"
        "🎯 Entrada\n"
        "🛑 Stop Loss\n"
        "💰 Take Profit\n"
        "⚖️ R:R\n"
        "📊 Riesgo estimado\n\n"
        "Actualmente esta sección está preparada "
        "para la futura integración del sistema "
        "de señales.\n\n"
        "⚠️ Las señales no garantizan resultados. "
        "El trading implica riesgo de pérdida."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# PLANES
# ============================================================

async def show_plans(query):
    text = (
        "💰 *Planes Apex Quant*\n\n"
        "Los siguientes porcentajes representan "
        "estimaciones de referencia y NO son "
        "rendimientos garantizados.\n\n"
        "🟢 *30 días*\n"
        "Estimación: *8%*\n\n"
        "🟢 *90 días*\n"
        "Estimación: *24%*\n\n"
        "🟢 *180 días*\n"
        "Estimación: *48%*\n\n"
        "🟢 *360 días*\n"
        "Estimación: *96%*\n\n"
        "La referencia de 360 días corresponde "
        "aproximadamente a un promedio simple del "
        "8% mensual y no significa que cada mes "
        "vaya a producir exactamente ese porcentaje.\n\n"
        "⚠️ *Importante:* los resultados pueden ser "
        "inferiores, superiores o negativos dependiendo "
        "de las condiciones del mercado. Existe riesgo "
        "de pérdida de capital.\n\n"
        "ℹ️ Las condiciones, comisiones, reglas de "
        "participación y retiros se definirán antes "
        "de la activación comercial."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# REFERIDOS
# ============================================================

async def show_referrals(query):
    user = query.from_user

    telegram_id = user.id

    invite_link = (
        f"https://t.me/ApexQuantFXBot?start=ref_{telegram_id}"
    )

    text = (
        "👥 *Programa de referidos Apex Quant*\n\n"
        "Invita a otras personas a conocer Apex Quant "
        "utilizando tu enlace personal.\n\n"
        "🔗 *Tu enlace personal:*\n"
        f"`{invite_link}`\n\n"
        "🆔 *Tu ID de Telegram:* "
        f"`{telegram_id}`\n\n"
        "👥 *Referidos registrados:* 0\n\n"
        "📊 Cada usuario tendrá un identificador único "
        "basado en su cuenta de Telegram.\n\n"
        "🔐 Esto permitirá posteriormente evitar "
        "referidos duplicados y detectar intentos "
        "de auto-referencia.\n\n"
        "⚠️ Las condiciones, comisiones y recompensas "
        "se establecerán antes de activar el programa "
        "comercial."
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
    keyboard = [
        [
            InlineKeyboardButton(
                "🇪🇸 Español",
                callback_data="lang_es",
            ),
            InlineKeyboardButton(
                "🇺🇸 English",
                callback_data="lang_en",
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ Menú principal",
                callback_data="main_menu",
            )
        ],
    ]

    text = (
        "🌐 *Idioma / Language*\n\n"
        "Selecciona el idioma que deseas utilizar."
    )

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
        "Aquí estarán disponibles próximamente "
        "las preferencias personales de tu cuenta.\n\n"
        "🔔 Notificaciones\n"
        "📡 Preferencias de señales\n"
        "🌐 Idioma\n"
        "👤 Preferencias de usuario"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


# ============================================================
# CALLBACKS
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

        text = (
            "🔥 *Apex Quant*\n\n"
            "Selecciona una opción:"
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

    # --------------------------------------------------------
    # MERCADOS
    # --------------------------------------------------------

    elif data == "markets":
        await show_markets(query)

    elif data == "signals":
        await show_signals(query)

    elif data == "plans":
        await show_plans(query)

    elif data == "referrals":
        await show_referrals(query)

    elif data == "language":
        await show_language(query)

    elif data == "settings":
        await show_settings(query)

    # --------------------------------------------------------
    # CALENDARIO
    # --------------------------------------------------------

    elif data == "calendar":
        await show_calendar(query)

    elif data == "calendar_today":

        today = today_date()

        await show_events(
            query,
            "Eventos de hoy",
            today,
            today,
        )

    elif data == "calendar_tomorrow":

        tomorrow = tomorrow_date()

        await show_events(
            query,
            "Eventos de mañana",
            tomorrow,
            tomorrow,
        )

    elif data == "calendar_week":

        monday, sunday = week_dates()

        await show_events(
            query,
            "Eventos de esta semana",
            monday,
            sunday,
        )

    elif data == "calendar_high":

        today = today_date()

        end_date = today + timedelta(days=7)

        await show_events(
            query,
            "Eventos de alto impacto",
            today,
            end_date,
            impact="high",
        )

    elif data == "calendar_currency":

        await show_currency_news(query)

    elif data == "calendar_refresh":

        today = today_date()

        await show_events(
            query,
            "Calendario actualizado",
            today,
            today,
        )

    # --------------------------------------------------------
    # NOTICIAS
    # --------------------------------------------------------

    elif data == "high_news":

        await show_high_news(query)

    elif data == "currency_news":

        await show_currency_news(query)

    elif data == "news_risk":

        await show_news_risk(query)

    elif data == "daily_analysis":

        await show_daily_analysis(query)

    # --------------------------------------------------------
    # DIVISAS
    # --------------------------------------------------------

    elif data.startswith("currency_"):

        currency = data.replace(
            "currency_",
            "",
        )

        await currency_events(
            query,
            currency,
        )

    # --------------------------------------------------------
    # IDIOMAS
    # --------------------------------------------------------

    elif data == "lang_es":

        await query.edit_message_text(
            "🇪🇸 *Español seleccionado.*\n\n"
            "La traducción completa de todas las "
            "secciones se integrará progresivamente.",
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )

    elif data == "lang_en":

        await query.edit_message_text(
            "🇺🇸 *English selected.*\n\n"
            "Full translation of all sections "
            "will be integrated progressively.",
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )


# ============================================================
# INICIO DEL BOT — POLLING
# ============================================================

def main():

    logger.info(
        "Starting Apex Quant Telegram Bot..."
    )

    logger.info(
        "Starting Telegram polling..."
    )

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
        CallbackQueryHandler(
            button_handler
        )
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
