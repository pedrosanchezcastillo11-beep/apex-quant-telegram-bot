# -*- coding: utf-8 -*-

import os
import logging

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
# TECLADOS
# ============================================================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton("📊 Mercados", callback_data="markets"),
            InlineKeyboardButton("📡 Señales", callback_data="signals"),
        ],
        [
            InlineKeyboardButton("💰 Planes", callback_data="plans"),
            InlineKeyboardButton("👥 Referidos", callback_data="referrals"),
        ],
        [
            InlineKeyboardButton("🌐 Idioma", callback_data="language"),
            InlineKeyboardButton("⚙️ Configuración", callback_data="settings"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


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


def calendar_menu():
    keyboard = [
        [
            InlineKeyboardButton("📅 Hoy", callback_data="calendar_today"),
            InlineKeyboardButton("📅 Mañana", callback_data="calendar_tomorrow"),
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
# /START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "🔥 *Bienvenido a Apex Quant*\n\n"
        "Tu centro de información y herramientas para mercados "
        "financieros.\n\n"
        "📊 Mercados\n"
        "📡 Señales\n"
        "💰 Planes\n"
        "👥 Referidos\n"
        "🌐 Idioma\n"
        "⚙️ Configuración\n\n"
        "Selecciona una opción para comenzar.\n\n"
        "⚠️ *Aviso de riesgo:* la información, análisis y "
        "señales no garantizan resultados. Los mercados financieros "
        "implican riesgo y pueden producir pérdidas."
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
        "Consulta información y análisis relacionados con los "
        "mercados financieros.\n\n"
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
        "Consulta eventos económicos que pueden generar "
        "volatilidad en los mercados.\n\n"
        "Selecciona el periodo que deseas consultar:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


async def calendar_placeholder(query, title):

    text = (
        f"📅 *{title}*\n\n"
        "Esta sección está preparada para integrar el calendario "
        "económico en tiempo real.\n\n"
        "Los eventos podrán clasificarse por impacto y divisa.\n\n"
        "⚠️ Los eventos económicos pueden provocar movimientos "
        "rápidos y significativos en los mercados."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=calendar_menu(),
    )


# ============================================================
# NOTICIAS
# ============================================================

async def show_high_news(query):

    text = (
        "🚨 *Noticias de alto impacto*\n\n"
        "Esta sección mostrará las noticias económicas de mayor "
        "impacto potencial sobre los mercados.\n\n"
        "⚠️ Durante noticias importantes puede aumentar "
        "considerablemente la volatilidad y el spread."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_main_menu(),
    )


async def show_news_risk(query):

    text = (
        "⚠️ *Riesgo de noticias*\n\n"
        "Antes de ejecutar una operación se recomienda comprobar "
        "si existen eventos económicos importantes relacionados "
        "con el activo.\n\n"
        "Una noticia puede invalidar una estructura técnica y "
        "provocar movimientos bruscos."
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


async def currency_placeholder(query, currency):

    text = (
        f"💱 *Noticias {currency}*\n\n"
        f"Próximamente Apex Quant mostrará los eventos económicos "
        f"relacionados con {currency}.\n\n"
        "⚠️ Esta información tendrá carácter informativo y no "
        "constituirá una garantía de resultados."
    )

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
        "La metodología de análisis contempla diferentes "
        "elementos técnicos y de estructura de mercado:\n\n"
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
        "⏱️ Marcos utilizados para el análisis:\n"
        "H1 • M15 • M3\n\n"
        "⚠️ El análisis es informativo. Ninguna configuración "
        "técnica garantiza una operación ganadora."
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
        "Cuando exista una oportunidad que cumpla los criterios "
        "establecidos, la señal podrá incluir:\n\n"
        "💱 Par\n"
        "📈 Dirección\n"
        "🎯 Entrada\n"
        "🛑 Stop Loss\n"
        "💰 Take Profit\n"
        "⚖️ R:R\n"
        "📊 Riesgo estimado\n\n"
        "Actualmente esta sección está preparada para la futura "
        "integración del sistema de señales.\n\n"
        "⚠️ Las señales no garantizan resultados. El trading "
        "implica riesgo de pérdida."
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
        "Los siguientes porcentajes representan estimaciones "
        "de referencia y NO son rendimientos garantizados.\n\n"
        "🟢 *30 días*\n"
        "Estimación: *8%*\n\n"
        "🟢 *90 días*\n"
        "Estimación: *24%*\n\n"
        "🟢 *180 días*\n"
        "Estimación: *48%*\n\n"
        "🟢 *360 días*\n"
        "Estimación: *96%*\n\n"
        "La referencia de 360 días corresponde aproximadamente "
        "a un promedio simple del 8% mensual y no significa que "
        "cada mes vaya a producir exactamente ese porcentaje.\n\n"
        "⚠️ *Importante:* los resultados pueden ser inferiores, "
        "superiores o negativos dependiendo de las condiciones "
        "del mercado. Existe riesgo de pérdida de capital.\n\n"
        "ℹ️ Las condiciones, comisiones, reglas de participación "
        "y retiros se definirán antes de la activación comercial."
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

    text = (
        "👥 *Programa de referidos*\n\n"
        "Invita a otras personas a conocer Apex Quant.\n\n"
        "Tu enlace personal de invitación y las condiciones "
        "del programa se habilitarán en una próxima versión.\n\n"
        "El sistema será diseñado para que las recompensas y "
        "comisiones sean claras y sostenibles."
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
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# CONFIGURACIÓN
# ============================================================

async def show_settings(query):

    text = (
        "⚙️ *Configuración*\n\n"
        "Aquí estarán disponibles próximamente las preferencias "
        "personales de tu cuenta.\n\n"
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

    elif data == "calendar":
        await show_calendar(query)

    elif data == "high_news":
        await show_high_news(query)

    elif data == "currency_news":
        await show_currency_news(query)

    elif data == "news_risk":
        await show_news_risk(query)

    elif data == "daily_analysis":
        await show_daily_analysis(query)

    elif data == "calendar_today":
        await calendar_placeholder(query, "Eventos de hoy")

    elif data == "calendar_tomorrow":
        await calendar_placeholder(query, "Eventos de mañana")

    elif data == "calendar_week":
        await calendar_placeholder(query, "Eventos de esta semana")

    elif data == "calendar_high":
        await calendar_placeholder(query, "Eventos de alto impacto")

    elif data == "calendar_currency":
        await show_currency_news(query)

    elif data == "calendar_refresh":
        await calendar_placeholder(query, "Calendario actualizado")

    elif data.startswith("currency_"):
        currency = data.replace("currency_", "")
        await currency_placeholder(query, currency)

    elif data == "lang_es":
        await query.edit_message_text(
            "🇪🇸 *Español seleccionado.*\n\n"
            "La traducción completa de todas las secciones "
            "se integrará progresivamente.",
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )

    elif data == "lang_en":
        await query.edit_message_text(
            "🇺🇸 *English selected.*\n\n"
            "Full translation of all sections will be integrated "
            "progressively.",
            parse_mode="Markdown",
            reply_markup=back_main_menu(),
        )


# ============================================================
# INICIO DEL BOT — POLLING
# ============================================================

def main():

    logger.info("Starting Apex Quant Telegram Bot...")
    logger.info("Starting Telegram polling...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CallbackQueryHandler(button_handler)
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
