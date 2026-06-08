import logging
import random
import asyncio
from datetime import datetime, time
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Дані
# ─────────────────────────────────────────────

RANDOM_QUESTIONS = [
    "☕ Кава чи чай? І чому кава, якщо ви все одно вибрали чай?",
    "🌙 Ви «сова» чи «жайворон»? А може ви просто «кажан» і живете вночі?",
    "🏝 Якби вам зараз подарували тиждень відпустки — куди б ви поїхали?",
    "🎮 Яка настільна гра у вас асоціюється з найкращим вечором?",
    "🍕 Ананас на піці: злочин чи смілива кулінарна ідея?",
    "🐾 Якби ви були твариною — якою і чому?",
    "📚 Остання книга/серіал що вас захопив? Рекомендуєте?",
    "🌳 Похід у ліс або вечір у кафе — що обираєте цими вихідними?",
    "🎵 Яку пісню ви слухаєте на repeat прямо зараз?",
    "🔮 Якби могли отримати одну суперздібність — яку б обрали?",
    "🏕 Намет у горах чи хостел у місті — що ваш стиль подорожі?",
    "😂 Розкажіть один факт про себе, який всіх здивує?",
    "🍦 Яка ваша секретна харчова слабкість?",
    "⏰ Якби можна було повернутися в будь-який час — куди б ви пішли?",
    "🎯 Який один скіл хотіли б опанувати цього року?",
]

DISCUSSION_TOPICS = [
    "🗣 Тема для обговорення: *Ідеальний вихідний день* — як він виглядає у вас?",
    "🗣 Тема: *Найкраще місце для зустрічі компанії* — кафе, парк, чиясь квартира чи ще щось?",
    "🗣 Тема: *Настільні ігри* — ваш топ-3? Або чому ви їх досі не спробували?",
    "🗣 Тема: *Походи та активний відпочинок* — хто за, хто проти, і чому?",
    "🗣 Тема: *Як познайомитися з новими людьми* — що спрацювало особисто у вас?",
    "🗣 Тема: *Кіно/серіал разом* — чи хтось хотів би організувати перегляд?",
    "🗣 Тема: *Місцеві скарби* — яке місце у нашому місті варто відвідати всій компанії?",
    "🗣 Тема: *Що вас заряджає енергією* після важкого тижня?",
]

ACTIVITY_POLL_OPTIONS = {
    "weekend": {
        "question": "🗓 Що плануєте на ці вихідні?",
        "options": ["Настільні ігри 🎲", "Похід/прогулянка 🥾", "Кафе/ресторан ☕", "Кіно/серіали 🎬", "Нічого конкретного 😴", "Щось інше (пишіть в чат!)"]
    },
    "boardgames": {
        "question": "🎲 Хто готовий зіграти в настільні ігри найближчим часом?",
        "options": ["Так, цього тижня! 🙌", "Так, наступного тижня", "Можливо, залежить від часу", "Поки не можу 😔"]
    },
    "hike": {
        "question": "🥾 Хто хотів би сходити в похід?",
        "options": ["Я в! 💪", "Залежить від маршруту", "Залежить від дати", "Не моє, але бажаю удачі 😄"]
    },
    "cafe": {
        "question": "☕ Хто за зустріч у кафе?",
        "options": ["Я! ☕", "Можливо", "Цього разу не зможу"]
    },
}


# ─────────────────────────────────────────────
# Команди
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Привіт! Я ваш груповий бот-організатор!*\n\n"
        "Ось що я вмію:\n"
        "📊 /poll — запустити опитування про активності\n"
        "🎲 /boardgames — опитування про настільні ігри\n"
        "🥾 /hike — опитування про похід\n"
        "☕ /cafe — опитування про зустріч у кафе\n"
        "💡 /organize — оголосити про свою ідею заходу\n"
        "❓ /question — поставити рандомне цікаве питання\n"
        "💬 /topic — почати обговорення теми\n"
        "ℹ️ /help — показати цю довідку\n\n"
        "Також я автоматично кидатиму цікаві питання у рандомний час! 🎉"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def poll_weekend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = ACTIVITY_POLL_OPTIONS["weekend"]
    await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=data["question"],
        options=data["options"],
        is_anonymous=False,
        allows_multiple_answers=True,
    )


async def poll_boardgames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = ACTIVITY_POLL_OPTIONS["boardgames"]
    await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=data["question"],
        options=data["options"],
        is_anonymous=False,
        allows_multiple_answers=False,
    )


async def poll_hike(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = ACTIVITY_POLL_OPTIONS["hike"]
    await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=data["question"],
        options=data["options"],
        is_anonymous=False,
        allows_multiple_answers=False,
    )


async def poll_cafe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = ACTIVITY_POLL_OPTIONS["cafe"]
    await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=data["question"],
        options=data["options"],
        is_anonymous=False,
        allows_multiple_answers=False,
    )


async def organize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "✏️ Напишіть що хочете організувати після команди.\n"
            "Приклад: `/organize Похід на Говерлу 15 червня! Хто з нами?`",
            parse_mode="Markdown"
        )
        return

    idea = " ".join(args)
    organizer = update.effective_user.first_name

    keyboard = [
        [
            InlineKeyboardButton("✅ Я в!", callback_data="org_yes"),
            InlineKeyboardButton("🤔 Може бути", callback_data="org_maybe"),
            InlineKeyboardButton("❌ Не зможу", callback_data="org_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"📣 *{organizer} пропонує:*\n\n"
        f"_{idea}_\n\n"
        f"Хто йде?"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def organize_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.first_name
    responses = {"org_yes": f"✅ {user} іде!", "org_maybe": f"🤔 {user} може бути", "org_no": f"❌ {user} не зможе"}
    response = responses.get(query.data, "")

    if response:
        await query.message.reply_text(response)


async def random_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = random.choice(RANDOM_QUESTIONS)
    await update.message.reply_text(f"❓ {question}")


async def discussion_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = random.choice(DISCUSSION_TOPICS)
    await update.message.reply_text(topic, parse_mode="Markdown")


# ─────────────────────────────────────────────
# Автоматичні повідомлення
# ─────────────────────────────────────────────

async def scheduled_random_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    # 50% шанс питання, 50% тема
    if random.random() < 0.5:
        text = f"❓ {random.choice(RANDOM_QUESTIONS)}"
    else:
        text = random.choice(DISCUSSION_TOPICS)

    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")


async def scheduled_weekend_poll(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    data = ACTIVITY_POLL_OPTIONS["weekend"]
    await context.bot.send_poll(
        chat_id=chat_id,
        question=data["question"],
        options=data["options"],
        is_anonymous=False,
        allows_multiple_answers=True,
    )


async def setup_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    # Видалити старі завдання для цього чату (якщо є)
    current_jobs = job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()

    # Рандомне питання кожні 8-16 годин
    interval_hours = random.randint(8, 16)
    job_queue.run_repeating(
        scheduled_random_message,
        interval=interval_hours * 3600,
        first=10,
        data={"chat_id": chat_id},
        name=str(chat_id)
    )

    # Опитування кожну п'ятницю о 10:00
    job_queue.run_daily(
        scheduled_weekend_poll,
        time=time(10, 0),
        days=(4,),  # 4 = п'ятниця
        data={"chat_id": chat_id},
        name=f"{chat_id}_friday"
    )

    await update.message.reply_text(
        "✅ *Автоматичні повідомлення увімкнено!*\n\n"
        "• Рандомні питання — кілька разів на день\n"
        "• Опитування про вихідні — щоп'ятниці о 10:00",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────
# Запуск
# ─────────────────────────────────────────────

def main():
    import os
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Встановіть змінну середовища BOT_TOKEN!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("poll", poll_weekend))
    app.add_handler(CommandHandler("boardgames", poll_boardgames))
    app.add_handler(CommandHandler("hike", poll_hike))
    app.add_handler(CommandHandler("cafe", poll_cafe))
    app.add_handler(CommandHandler("organize", organize))
    app.add_handler(CommandHandler("question", random_question))
    app.add_handler(CommandHandler("topic", discussion_topic))
    app.add_handler(CommandHandler("autostart", setup_jobs))
    app.add_handler(CallbackQueryHandler(organize_callback, pattern="^org_"))

    logger.info("Бот запущено!")
    app.run_polling()


if __name__ == "__main__":
    main()
