```python
# -*- coding: utf-8 -*-

import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ============================================================
# APEX QUANT TELEGRAM BOT
# Versión 1.0
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

PLAN_RISK_NOTICE = """
⚠️ *AVISO IMPORTANTE*

Los porcentajes mostrados son *estimaciones* y no representan una promesa ni una garantía de rendimiento.

El rendimiento real puede ser inferior, superior o negativo según las condiciones del mercado. El capital está sujeto a riesgo y pueden producirse pérdidas.
"""


# ------------------------------------------------------------
# MENÚ PRINCIPAL
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# MENÚ DE MERCADOS
# ------------------------------------------------------------

def markets_menu():
    keyboard = [
        [InlineKeyboardButton("🗓️ Calendario económico", callback_data="calendar")],
        [InlineKeyboardButton("🔴 Noticias de alto impacto", callback_data="high_impact")],
        [InlineKeyboardButton("💱 Noticias por moneda", callback_data="currencies")],
        [InlineKeyboardButton("⚠️ Riesgo de noticias", callback_data="news_risk")],
        [InlineKeyboardButton("📈 Análisis del día", callback_data="daily_analysis")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# CALENDARIO ECONÓMICO
# ------------------------------------------------------------

def calendar_menu():
    keyboard = [
        [
            InlineKeyboardButton("📅 Hoy", callback_data="calendar_today"),
            InlineKeyboardButton("📅 Mañana", callback_data="calendar_tomorrow"),
        ],
        [InlineKeyboardButton("📆 Esta semana", callback_data="calendar_week")],
        [InlineKeyboardButton("🔴 Alto impacto", callback_data="high_impact")],
        [InlineKeyboardButton("💱 Por moneda", callback_data="currencies")],
        [InlineKeyboardButton("🔄 Actualizar", callback_data="calendar")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="markets")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# MONEDAS
# ------------------------------------------------------------

def currencies_menu():
    keyboard = [
        [
            InlineKeyboardButton("🇺🇸 USD", callback_data="currency_USD"),
            InlineKeyboardButton("🇪🇺 EUR", callback_data="currency_EUR"),
        ],
        [
            InlineKeyboardButton("🇬🇧 GBP", callback_data="currency_GBP"),
            InlineKeyboardButton("🇯🇵 JPY", callback_data="currency_JPY"),
        ],
        [
            InlineKeyboardButton("🇨🇭 CHF", callback_data="currency_CHF"),
            InlineKeyboardButton("🇨🇦 CAD", callback_data="currency_CAD"),
        ],
        [
            InlineKeyboardButton("🇦🇺 AUD", callback_data="currency_AUD"),
            InlineKeyboardButton("🇳🇿 NZD", callback_data="currency_NZD"),
        ],
        [InlineKeyboardButton("⬅️ Volver", callback_data="markets")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# PLANES
# ------------------------------------------------------------

def plans_menu():
    keyboard = [
        [InlineKeyboardButton("📅 Plan 30 días — 8% estimado", callback_data="plan_30")],
        [InlineKeyboardButton("📅 Plan 90 días — 24% estimado", callback_data="plan_90")],
        [InlineKeyboardButton("📅 Plan 180 días — 48% estimado", callback_data="plan_180")],
        [InlineKeyboardButton("📅 Plan 360 días — 96% estimado", callback_data="plan_360")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# IDIOMA
# ------------------------------------------------------------

def language_menu():
    keyboard = [
        [
            InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es"),
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
        ],
        [InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------------------------

def settings_menu():
    keyboard = [
        [InlineKeyboardButton("🔔 Notificaciones", callback_data="notifications")],
        [InlineKeyboardButton("⚙️ Preferencias", callback_data="preferences")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# BIENVENIDA
# ------------------------------------------------------------

WELCOME_MESSAGE = """
🚀 *Bienvenido a Apex Quant*

Tu centro de análisis y herramientas para los mercados financieros.

Desde aquí podrás consultar el calendario económico, identificar eventos de alto impacto, recibir información de mercado y acceder a las diferentes funciones de Apex Quant.

⚠️ *Aviso de riesgo:* Los mercados financieros implican riesgo y los resultados no están garantizados. La información proporcionada por Apex Quant tiene carácter informativo y educativo y no constituye una garantía de resultados.

*Selecciona una opción para comenzar:*
"""


# ------------------------------------------------------------
# COMANDO /START
# ------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ------------------------------------------------------------
# MANEJO DE BOTONES
# ------------------------------------------------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # -------------------------
    # MENÚ PRINCIPAL
    # -------------------------

    if data == "main_menu":
        await query.edit_message_text(
            WELCOME_MESSAGE,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

    # -------------------------
    # MERCADOS
    # -------------------------

    elif data == "markets":
        await query.edit_message_text(
            "📊 *MERCADOS*\n\nSelecciona una opción:",
            parse_mode="Markdown",
            reply_markup=markets_menu(),
        )

    # -------------------------
    # CALENDARIO
    # -------------------------

    elif data == "calendar":
        text = """
🗓️ *CALENDARIO ECONÓMICO*

Selecciona el período que deseas consultar.

📌 Próximamente este módulo se conectará a datos económicos en tiempo real.
"""
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

    # -------------------------
    # CALENDARIO HOY
    # -------------------------

    elif data == "calendar_today":
        await query.edit_message_text(
            """
📅 *CALENDARIO — HOY*

🔴 Próximamente mostraremos aquí los eventos económicos del día.

Los eventos serán clasificados por:

🔴 Alto impacto
🟠 Impacto medio
🟢 Bajo impacto

⚠️ Los horarios dependerán de la zona horaria configurada.
""",
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

    # -------------------------
    # CALENDARIO MAÑANA
    # -------------------------

    elif data == "calendar_tomorrow":
        await query.edit_message_text(
            """
📅 *CALENDARIO — MAÑANA*

🔴 Próximamente mostraremos aquí los eventos económicos de mañana.

Cada evento incluirá:

⏰ Hora
🌎 País
💱 Moneda
📊 Previsión
📉 Anterior
🔴 Nivel de impacto
🎯 Pares potencialmente afectados
""",
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

    # -------------------------
    # ESTA SEMANA
    # -------------------------

    elif data == "calendar_week":
        await query.edit_message_text(
            """
📆 *CALENDARIO — ESTA SEMANA*

Aquí aparecerán los principales eventos económicos de la semana.

🔴 Alto impacto
🟠 Impacto medio
🟢 Bajo impacto

El calendario será conectado posteriormente a datos actualizados.
""",
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

    # -------------------------
    # ALTO IMPACTO
    # -------------------------

    elif data == "high_impact":
        await query.edit_message_text(
            """
🔴 *NOTICIAS DE ALTO IMPACTO*

Esta sección mostrará exclusivamente eventos con potencial de generar una elevada volatilidad.

Ejemplo:

🇺🇸 USD
📊 Decisión de tipos
⏰ Hora del evento
🎯 EUR/USD • GBP/USD • USD/JPY

🇬🇧 GBP
📊 Decisión del BoE
🎯 GBP/USD • GBP/JPY

🇯🇵 JPY
📊 Decisión del BoJ
🎯 GBP/JPY • USD/JPY

⚠️ Una noticia de alto impacto puede provocar movimientos rápidos, spreads elevados y slippage.
""",
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

    # -------------------------
    # MONEDAS
    # -------------------------

    elif data == "currencies":
        await query.edit_message_text(
            "💱 *NOTICIAS POR MONEDA*\n\nSelecciona una moneda:",
            parse_mode="Markdown",
            reply_markup=currencies_menu(),
        )

    # -------------------------
    # MONEDA
    # -------------------------

    elif data.startswith("currency_"):
        currency = data.replace("currency_", "")
        await query.edit_message_text(
            f"""
💱 *NOTICIAS — {currency}*

Aquí aparecerán próximamente los eventos económicos relacionados con {currency}.

También mostraremos los principales pares afectados y el nivel de impacto.

⚠️ La reacción del mercado no está garantizada y depende del contexto económico y de las expectativas del mercado.
""",
            parse_mode="Markdown",
            reply_markup=currencies_menu(),
        )

    # -------------------------
    # RIESGO
    # -------------------------

    elif data == "news_risk":
        await query.edit_message_text(
            """
⚠️ *RIESGO DE NOTICIAS*

🔴 *ALTO*
Eventos importantes próximos. Se recomienda extremar la precaución.

🟠 *MEDIO*
Puede producirse volatilidad moderada.

🟢 *BAJO*
No se identifican eventos relevantes próximos.

📌 Apex Quant utilizará esta información como parte del contexto de mercado.

⚠️ La clasificación no garantiza la dirección ni la magnitud del movimiento.
""",
            parse_mode="Markdown",
            reply_markup=markets_menu(),
        )

    # -------------------------
    # ANÁLISIS DEL DÍA
    # -------------------------

    elif data == "daily_analysis":
        await query.edit_message_text(
            """
📈 *ANÁLISIS DEL DÍA*

Próximamente esta sección combinará:

🗓️ Calendario económico
📊 Noticias fundamentales
📈 Estructura del mercado
🔎 BOS
🧩 FVG
💧 Liquidez
📊 Volumen
📉 RSI

🎯 Pares principales:

EUR/USD
GBP/USD
GBP/JPY

⚠️ El análisis no garantiza resultados.
""",
            parse_mode="Markdown",
            reply_markup=markets_menu(),
        )

    # -------------------------
    # SEÑALES
    # -------------------------

    elif data == "signals":
        await query.edit_message_text(
            """
📡 *SEÑALES APEX QUANT*

Próximamente esta sección permitirá consultar las señales disponibles.

Cada señal podrá incluir:

💱 Par
📈 Dirección
🎯 Entrada
🛑 Stop Loss
💰 Take Profit
📊 Relación R:R
⚠️ Nivel de riesgo

⚠️ Las señales no garantizan resultados. El trading implica riesgo.
""",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

    # -------------------------
    # PLANES
    # -------------------------

    elif data == "plans":
        await query.edit_message_text(
            f"""
💰 *PLANES APEX QUANT*

Selecciona un plan para consultar sus características.

📌 *Planes disponibles:*
• 30 días — 8% estimado
• 90 días — 24% estimado
• 180 días — 48% estimado
• 360 días — 96% estimado

{PLAN_RISK_NOTICE}
""",
            parse_mode="Markdown",
            reply_markup=plans_menu(),
        )

    # -------------------------
    # PLAN 30
    # -------------------------

    elif data == "plan_30":
        await query.edit_message_text(
            f"""
📅 *PLAN 30 DÍAS*

📊 Rendimiento estimado: *8%*

{PLAN_RISK_NOTICE}
""",
            parse_mode="Markdown",
            reply_markup=plans_menu(),
        )

    # -------------------------
    # PLAN 90
    # -------------------------

    elif data == "plan_90":
        await query.edit_message_text(
            f"""
📅 *PLAN 90 DÍAS*

📊 Rendimiento estimado: *24%*

{PLAN_RISK_NOTICE}
""",
            parse_mode="Markdown",
            reply_markup=plans_menu(),
        )

    # -------------------------
    # PLAN 180
    # -------------------------

    elif data == "plan_180":
        await query.edit_message_text(
            f"""
📅 *PLAN 180 DÍAS*

📊 Rendimiento estimado: *48%*

{PLAN_RISK_NOTICE}
""",
            parse_mode="Markdown",
            reply_markup=plans_menu(),
        )

    # -------------------------
    # PLAN 360
    # -------------------------

    elif data == "plan_360":
        await query.edit_message_text(
            f"""
📅 *PLAN 360 DÍAS*

📊 Rendimiento estimado: *96%*

📌 Este porcentaje corresponde a una referencia anual estimada equivalente a un promedio simple de aproximadamente 8% mensual; no implica que el rendimiento se produzca de forma uniforme cada mes.

{PLAN_RISK_NOTICE}
""",
            parse_mode="Markdown",
            reply_markup=plans_menu(),
        )

    # -------------------------
    # REFERIDOS
    # -------------------------

    elif data == "referrals":
        await query.edit_message_text(
            """
👥 *PROGRAMA DE REFERIDOS*

Invita a otras personas a conocer Apex Quant.

🔗 Próximamente cada usuario tendrá su enlace personal de invitación.

📊 También podremos mostrar:
• Invitaciones
• Usuarios registrados
• Recompensas disponibles

⚠️ Las condiciones del programa estarán sujetas a las reglas oficiales de Apex Quant.
""",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

    # -------------------------
    # IDIOMA
    # -------------------------

    elif data == "language":
        await query.edit_message_text(
            "🌐 *SELECCIONA TU IDIOMA*",
            parse_mode="Markdown",
            reply_markup=language_menu(),
        )

    elif data == "lang_es":
        await query.edit_message_text(
            "🇪🇸 *Español seleccionado*",
            parse_mode="Markdown",
            reply_markup=language_menu(),
        )

    elif data == "lang_en":
        await query.edit_message_text(
            "🇺🇸 *English selected*",
            parse_mode="Markdown",
            reply_markup=language_menu(),
        )

    # -------------------------
    # CONFIGURACIÓN
    # -------------------------

    elif data == "settings":
        await query.edit_message_text(
            "⚙️ *CONFIGURACIÓN*\n\nSelecciona una opción:",
            parse_mode="Markdown",
            reply_markup=settings_menu(),
        )

    elif data == "notifications":
        await query.answer("🔔 Las notificaciones se configurarán próximamente.")

    elif data == "preferences":
        await query.answer("⚙️ Las preferencias se configurarán próximamente.")


# ------------------------------------------------------------
# INICIAR BOT
# ------------------------------------------------------------

def main():
    if not BOT_TOKEN:
        raise ValueError(
            "No se encontró BOT_TOKEN. "
            "Configura la variable de entorno BOT_TOKEN."
        )

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🚀 Apex Quant Bot iniciado correctamente.")

    application.run_polling()


if __name__ == "__main__":
    main()
```
