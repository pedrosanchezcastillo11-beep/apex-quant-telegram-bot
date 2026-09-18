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
# VersiÃ³n 1.1
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ------------------------------------------------------------
# MENÃš PRINCIPAL
# ------------------------------------------------------------

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton("ðŸ“Š Mercados", callback_data="markets"),
            InlineKeyboardButton("ðŸ“¡ SeÃ±ales", callback_data="signals"),
        ],
        [
            InlineKeyboardButton("ðŸ’° Planes", callback_data="plans"),
            InlineKeyboardButton("ðŸ‘¥ Referidos", callback_data="referrals"),
        ],
        [
            InlineKeyboardButton("ðŸŒ Idioma", callback_data="language"),
            InlineKeyboardButton("âš™ï¸ ConfiguraciÃ³n", callback_data="settings"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# MENÃš DE MERCADOS
# ------------------------------------------------------------

def markets_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ—“ï¸ Calendario econÃ³mico",
                callback_data="calendar",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ”´ Noticias de alto impacto",
                callback_data="high_impact",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ’± Noticias por moneda",
                callback_data="currencies",
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
                "ðŸ“ˆ AnÃ¡lisis del dÃ­a",
                callback_data="daily_analysis",
            )
        ],
        [
            InlineKeyboardButton("â¬…ï¸ Volver", callback_data="main_menu")
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# CALENDARIO ECONÃ“MICO
# ------------------------------------------------------------

def calendar_menu():
    keyboard = [
        [
            InlineKeyboardButton("ðŸ“… Hoy", callback_data="calendar_today"),
            InlineKeyboardButton("ðŸ“… MaÃ±ana", callback_data="calendar_tomorrow"),
        ],
        [
            InlineKeyboardButton(
                "ðŸ“† Esta semana",
                callback_data="calendar_week",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ”´ Alto impacto",
                callback_data="high_impact",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ’± Por moneda",
                callback_data="currencies",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ”„ Actualizar",
                callback_data="calendar",
            )
        ],
        [
            InlineKeyboardButton("â¬…ï¸ Volver", callback_data="markets")
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# MONEDAS
# ------------------------------------------------------------

def currencies_menu():
    keyboard = [
        [
            InlineKeyboardButton("ðŸ‡ºðŸ‡¸ USD", callback_data="currency_USD"),
            InlineKeyboardButton("ðŸ‡ªðŸ‡º EUR", callback_data="currency_EUR"),
        ],
        [
            InlineKeyboardButton("ðŸ‡¬ðŸ‡§ GBP", callback_data="currency_GBP"),
            InlineKeyboardButton("ðŸ‡¯ðŸ‡µ JPY", callback_data="currency_JPY"),
        ],
        [
            InlineKeyboardButton("ðŸ‡¨ðŸ‡­ CHF", callback_data="currency_CHF"),
            InlineKeyboardButton("ðŸ‡¨ðŸ‡¦ CAD", callback_data="currency_CAD"),
        ],
        [
            InlineKeyboardButton("ðŸ‡¦ðŸ‡º AUD", callback_data="currency_AUD"),
            InlineKeyboardButton("ðŸ‡³ðŸ‡¿ NZD", callback_data="currency_NZD"),
        ],
        [
            InlineKeyboardButton("â¬…ï¸ Volver", callback_data="markets")
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# PLANES
# ------------------------------------------------------------

def plans_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ“… Plan 30 dÃ­as â€” 8% estimado",
                callback_data="plan_30",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ“… Plan 90 dÃ­as â€” 24% estimado",
                callback_data="plan_90",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ“… Plan 180 dÃ­as â€” 48% estimado",
                callback_data="plan_180",
            )
        ],
        [
            InlineKeyboardButton(
                "ðŸ“… Plan 360 dÃ­as â€” 96% estimado",
                callback_data="plan_360",
            )
        ],
        [
            InlineKeyboardButton("â¬…ï¸ Volver", callback_data="main_menu")
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# IDIOMA
# ------------------------------------------------------------

def language_menu():
    keyboard = [
        [
            InlineKeyboardButton("ðŸ‡ªðŸ‡¸ EspaÃ±ol", callback_data="lang_es"),
            InlineKeyboardButton("ðŸ‡ºðŸ‡¸ English", callback_data="lang_en"),
        ],
        [
            InlineKeyboardButton("â¬…ï¸ Volver", callback_data="main_menu")
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# CONFIGURACIÃ“N
# ------------------------------------------------------------

def settings_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "ðŸ”” Notificaciones",
                callback_data="notifications",
            )
        ],
        [
            InlineKeyboardButton(
                "âš™ï¸ Preferencias",
                callback_data="preferences",
            )
        ],
        [
            InlineKeyboardButton("â¬…ï¸ Volver", callback_data="main_menu")
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------
# BIENVENIDA
# ------------------------------------------------------------

WELCOME_MESSAGE = """
ðŸš€ *Bienvenido a Apex Quant*

Tu centro de anÃ¡lisis y herramientas para los mercados financieros.

Desde aquÃ­ podrÃ¡s consultar el calendario econÃ³mico, identificar eventos de alto impacto, recibir informaciÃ³n de mercado y acceder a las diferentes funciones de Apex Quant.

âš ï¸ *Aviso de riesgo:* Los mercados financieros implican riesgo y los resultados no estÃ¡n garantizados. La informaciÃ³n proporcionada por Apex Quant tiene carÃ¡cter informativo y educativo y no constituye una garantÃ­a de resultados.

*Selecciona una opciÃ³n para comenzar:*
"""


# ------------------------------------------------------------
# AVISO DE PLANES
# ------------------------------------------------------------

PLAN_RISK_NOTICE = """
âš ï¸ *AVISO IMPORTANTE*

Los porcentajes mostrados son *estimaciones* y no representan una promesa ni una garantÃ­a de rendimiento.

El rendimiento real puede ser inferior, superior o negativo segÃºn las condiciones del mercado. El capital estÃ¡ sujeto a riesgo y pueden producirse pÃ©rdidas.
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

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    data = query.data

    # -------------------------
    # MENÃš PRINCIPAL
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
            "ðŸ“Š *MERCADOS*\n\nSelecciona una opciÃ³n:",
            parse_mode="Markdown",
            reply_markup=markets_menu(),
        )

    # -------------------------
    # CALENDARIO
    # -------------------------

    elif data == "calendar":
        text = """
ðŸ—“ï¸ *CALENDARIO ECONÃ“MICO*

Selecciona el perÃ­odo que deseas consultar.

ðŸ“Œ PrÃ³ximamente este mÃ³dulo se conectarÃ¡ a datos econÃ³micos en tiempo real.
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
ðŸ“… *CALENDARIO â€” HOY*

ðŸ”´ PrÃ³ximamente mostraremos aquÃ­ los eventos econÃ³micos del dÃ­a.

Los eventos serÃ¡n clasificados por:

ðŸ”´ Alto impacto
ðŸŸ  Impacto medio
ðŸŸ¢ Bajo impacto

âš ï¸ Los horarios dependerÃ¡n de la zona horaria configurada.
""",
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

    # -------------------------
    # CALENDARIO MAÃ‘ANA
    # -------------------------

    elif data == "calendar_tomorrow":
        await query.edit_message_text(
            """
ðŸ“… *CALENDARIO â€” MAÃ‘ANA*

ðŸ”´ PrÃ³ximamente mostraremos aquÃ­ los eventos econÃ³micos de maÃ±ana.

Cada evento incluirÃ¡:

â° Hora
ðŸŒŽ PaÃ­s
ðŸ’± Moneda
ðŸ“Š PrevisiÃ³n
ðŸ“‰ Anterior
ðŸ”´ Nivel de impacto
ðŸŽ¯ Pares potencialmente afectados
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
ðŸ“† *CALENDARIO â€” ESTA SEMANA*

AquÃ­ aparecerÃ¡n los principales eventos econÃ³micos de la semana.

ðŸ”´ Alto impacto
ðŸŸ  Impacto medio
ðŸŸ¢ Bajo impacto

El calendario serÃ¡ conectado posteriormente a datos actualizados.
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
ðŸ”´ *NOTICIAS DE ALTO IMPACTO*

Esta secciÃ³n mostrarÃ¡ exclusivamente eventos con potencial de generar una elevada volatilidad.

Ejemplo:

ðŸ‡ºðŸ‡¸ USD
ðŸ“Š DecisiÃ³n de tipos
â° Hora del evento
ðŸŽ¯ EUR/USD â€¢ GBP/USD â€¢ USD/JPY

ðŸ‡¬ðŸ‡§ GBP
ðŸ“Š DecisiÃ³n del BoE
ðŸŽ¯ GBP/USD â€¢ GBP/JPY

ðŸ‡¯ðŸ‡µ JPY
ðŸ“Š DecisiÃ³n del BoJ
ðŸŽ¯ GBP/JPY â€¢ USD/JPY

âš ï¸ Una noticia de alto impacto puede provocar movimientos rÃ¡pidos, spreads elevados y slippage.
""",
            parse_mode="Markdown",
            reply_markup=calendar_menu(),
        )

    # -------------------------
    # MONEDAS
    # -------------------------

    elif data == "currencies":
        await query.edit_message_text(
            "ðŸ’± *NOTICIAS POR MONEDA*\n\nSelecciona una moneda:",
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
ðŸ’± *NOTICIAS â€” {currency}*

AquÃ­ aparecerÃ¡n prÃ³ximamente los eventos econÃ³micos relacionados con {currency}.

TambiÃ©n mostraremos los principales pares afectados y el nivel de impacto.

âš ï¸ La reacciÃ³n del mercado no estÃ¡ garantizada y depende del contexto econÃ³mico y de las expectativas del mercado.
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
âš ï¸ *RIESGO DE NOTICIAS*

ðŸ”´ *ALTO*
Eventos importantes prÃ³ximos. Se recomienda extremar la precauciÃ³n.

ðŸŸ  *MEDIO*
Puede producirse volatilidad moderada.

ðŸŸ¢ *BAJO*
No se identifican eventos relevantes prÃ³ximos.

ðŸ“Œ Apex Quant utilizarÃ¡ esta informaciÃ³n como parte del contexto de mercado.

âš ï¸ La clasificaciÃ³n no garantiza la direcciÃ³n ni la magnitud del movimiento.
""",
            parse_mode="Markdown",
            reply_markup=markets_menu(),
        )

    # -------------------------
    # ANÃLISIS DEL DÃA
    # -------------------------

    elif data == "daily_analysis":
        await query.edit_message_text(
            """
ðŸ“ˆ *ANÃLISIS DEL DÃA*

PrÃ³ximamente esta secciÃ³n combinarÃ¡:

ðŸ—“ï¸ Calendario econÃ³mico
ðŸ“Š Noticias fundamentales
ðŸ“ˆ Estructura del mercado
ðŸ”Ž BOS
ðŸ§© FVG
ðŸ’§ Liquidez
ðŸ“Š Volumen
ðŸ“‰ RSI

ðŸŽ¯ Pares principales:

EUR/USD
GBP/USD
GBP/JPY

âš ï¸ El anÃ¡lisis no garantiza resultados.
""",
            parse_mode="Markdown",
            reply_markup=markets_menu(),
        )

    # -------------------------
    # SEÃ‘ALES
    # -------------------------

    elif data == "signals":
        await query.edit_message_text(
            """
ðŸ“¡ *SEÃ‘ALES APEX QUANT*

PrÃ³ximamente esta secciÃ³n permitirÃ¡ consultar las seÃ±ales disponibles.

Cada seÃ±al podrÃ¡ incluir:

ðŸ’± Par
ðŸ“ˆ DirecciÃ³n
ðŸŽ¯ Entrada
ðŸ›‘ Stop Loss
ðŸ’° Take Profit
ðŸ“Š RelaciÃ³n R:R
âš ï¸ Nivel de riesgo

âš ï¸ Las seÃ±ales no garantizan resultados. El trading implica riesgo.
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
ðŸ’° *PLANES APEX QUANT*

Selecciona un plan para consultar sus caracterÃ­sticas.

ðŸ“Œ *Planes disponibles:*
â€¢ 30 dÃ­as â€” 8% estimado
â€¢ 90 dÃ­as â€” 24% estimado
â€¢ 180 dÃ­as â€” 48% estimado
â€¢ 360 dÃ­as â€” 96% estimado

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
ðŸ“… *PLAN 30 DÃAS*

ðŸ“Š Rendimiento estimado: *8%*

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
ðŸ“… *PLAN 90 DÃAS*

ðŸ“Š Rendimiento estimado: *24%*

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
ðŸ“… *PLAN 180 DÃAS*

ðŸ“Š Rendimiento estimado: *48%*

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
ðŸ“… *PLAN 360 DÃAS*

ðŸ“Š Rendimiento estimado: *96%*

ðŸ“Œ Este porcentaje corresponde a una referencia anual estimada equivalente a un promedio simple de aproximadamente 8% mensual; no implica que el rendimiento se produzca de forma uniforme cada mes.

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
ðŸ‘¥ *PROGRAMA DE REFERIDOS*

Invita a otras personas a conocer Apex Quant.

ðŸ”— PrÃ³ximamente cada usuario tendrÃ¡ su enlace personal de invitaciÃ³n.

ðŸ“Š TambiÃ©n podremos mostrar:
â€¢ Invitaciones
â€¢ Usuarios registrados
â€¢ Recompensas disponibles

âš ï¸ Las condiciones del programa estarÃ¡n sujetas a las reglas oficiales de Apex Quant.
""",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

    # -------------------------
    # IDIOMA
    # -------------------------

    elif data == "language":
        await query.edit_message_text(
            "ðŸŒ *SELECCIONA TU IDIOMA*",
            parse_mode="Markdown",
            reply_markup=language_menu(),
        )

    elif data == "lang_es":
        await query.edit_message_text(
            "ðŸ‡ªðŸ‡¸ *EspaÃ±ol seleccionado.*\n\nEl idioma espaÃ±ol ya estÃ¡ activo.",
            parse_mode="Markdown",
            reply_markup=language_menu(),
        )

    elif data == "lang_en":
        await query.edit_message_text(
            "ðŸ‡ºðŸ‡¸ *English selected.*\n\nEnglish support will be expanded in a future update.",
            parse_mode="Markdown",
            reply_markup=language_menu(),
        )

    # -------------------------
    # CONFIGURACIÃ“N
    # -------------------------

    elif data == "settings":
        await query.edit_message_text(
            "âš™ï¸ *CONFIGURACIÃ“N*\n\nSelecciona una opciÃ³n:",
            parse_mode="Markdown",
            reply_markup=settings_menu(),
        )

    elif data == "notifications":
        await query.answer(
            "ðŸ”” Las notificaciones se configurarÃ¡n prÃ³ximamente."
        )

    elif data == "preferences":
        await query.answer(
            "âš™ï¸ Las preferencias se configurarÃ¡n prÃ³ximamente."
        )


# ------------------------------------------------------------
# INICIAR BOT
# ------------------------------------------------------------

def main():
    if not BOT_TOKEN:
        raise ValueError(
            "No se encontrÃ³ BOT_TOKEN. "
            "Configura la variable de entorno BOT_TOKEN."
        )

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        CallbackQueryHandler(button_handler)
    )

    print("ðŸš€ Apex Quant Bot iniciado correctamente.")

    application.run_polling()


if __name__ == "__main__":
    main()
