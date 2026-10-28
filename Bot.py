import json
import os
import requests
import asyncio
from difflib import get_close_matches
from database import (
    initialize_database,
    add_monitor,
    get_active_monitors,
    deactivate_monitor,
)
from groq import AsyncGroq
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

groq_client = AsyncGroq(
    api_key=os.getenv("GROQ_API_KEY")
)

SYSTEM_PROMPT = """
You are Abed AI Agent, a personal AI assistant created by Abed Rteil.

Your identity:
- Your name is Abed AI Agent.
- You were built as a Python Telegram bot.
- You use Groq's API to access the GPT-OSS 120B model.
- You are not ChatGPT and do not run through OpenAI's ChatGPT service.

When asked who you are, introduce yourself as Abed AI Agent.
Be friendly, helpful, clear, and concise.
Never claim to have capabilities you do not possess.
"""


# START COMMAND
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! 👋 I'm Abed AI Agent, your personal AI assistant.\n\n"
        "Ask me anything by simply sending a message!\n\n"
        "🌤️ You can also use /weather Beirut to check the weather."
    )

async def monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "Use this format:\n"
            "/monitor Beirut below 20\n"
            "/monitor Nabatieh above 30"
        )
        return

    city = " ".join(context.args[:-2])
    condition = context.args[-2].lower()

    try:
        threshold = float(context.args[-1])
    except ValueError:
        await update.message.reply_text(
            "The temperature must be a number, like 20."
        )
        return

    if condition not in ("below", "above"):
        await update.message.reply_text(
            "Use 'below' or 'above'."
        )
        return

    chat_id = update.effective_chat.id

    monitor_id = await add_monitor(
        chat_id, city, condition, threshold
    )

    await update.message.reply_text(
        f"✅ Monitor created!\n\n"
        f"📍 City: {city}\n"
        f"🌡️ Alert when temperature is {condition} "
        f"{threshold}°C\n"
        f"🆔 Monitor ID: {monitor_id}"
    )


# LIST ACTIVE MONITORS
async def monitors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_monitors = await get_active_monitors()

    # Show only monitors belonging to this Telegram chat.
    my_monitors = [
        item for item in active_monitors
        if str(item["chat_id"]) == str(chat_id)
    ]

    if not my_monitors:
        await update.message.reply_text(
            "📋 You have no active monitors.\n\n"
            "Create a temperature monitor using:\n"
            "/monitor Beirut below 20\n\n"
            "Or ask me to alert you if rain is expected in Beirut."
        )
        return

    lines = ["📋 Your Active Monitors\n"]

    for item in my_monitors:
        if item["condition"] == "rain":
            description = (
                "🌧️ Alert when rain is expected "
                "in the next 2 hours"
            )
        else:
            description = (
                f"🌡️ Alert when temperature is "
                f"{item['condition']} {item['threshold']}°C"
            )

        lines.append(
            f"🆔 ID: {item['id']}\n"
            f"📍 City: {item['city']}\n"
            f"{description}\n"
        )

    lines.append(
        "To stop a monitor, use:\n"
        "/cancelmonitor ID"
    )

    await update.message.reply_text("\n".join(lines))



# CANCEL AN ACTIVE MONITOR
async def cancelmonitor(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not context.args:
        await update.message.reply_text(
            "Please provide a monitor ID.\n\n"
            "Example: /cancelmonitor 2\n\n"
            "Use /monitors to see your active monitor IDs."
        )
        return

    try:
        monitor_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Monitor ID must be a number.\n"
            "Example: /cancelmonitor 2"
        )
        return

    chat_id = update.effective_chat.id
    active_monitors = await get_active_monitors()

    # Only allow the owner of the monitor to cancel it.
    selected_monitor = next(
        (
            item for item in active_monitors
            if int(item["id"]) == monitor_id
            and str(item["chat_id"]) == str(chat_id)
        ),
        None,
    )

    if selected_monitor is None:
        await update.message.reply_text(
            "❌ I couldn't find that active monitor in your chat.\n\n"
            "Use /monitors to see your active monitors."
        )
        return

    # Deactivate the selected monitor.
    await deactivate_monitor(monitor_id)

    # Display the correct monitor type.
    if selected_monitor["condition"] == "rain":
        description = "🌧️ Rain forecast alert"
    else:
        description = (
            f"🌡️ Temperature {selected_monitor['condition']} "
            f"{selected_monitor['threshold']}°C"
        )

    await update.message.reply_text(
        f"🛑 Monitor {monitor_id} cancelled successfully.\n\n"
        f"📍 City: {selected_monitor['city']}\n"
        f"{description}"
    )



async def post_init(app: Application):
    await initialize_database()    


# AI RESPONSE FUNCTION
async def answer_question(update: Update, question: str):
    if not question.strip():
        await update.message.reply_text("Send me a question!")
        return

    try:
        response = await groq_client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ],
    tools=[{"type": "browser_search"}],
)
       

        answer = (
            response.choices[0].message.content
            or "Sorry, I couldn't generate an answer."
        )

        # Split long answers into Telegram-sized messages
        max_length = 4000

        for i in range(0, len(answer), max_length):
            await update.message.reply_text(
                answer[i:i + max_length]
            )

    except Exception as error:
        print("AI error:", error)
        await update.message.reply_text(
            "Sorry, something went wrong while generating "
            "my answer. Please try again."
        )


# NORMAL TEXT MESSAGES: NO /ask NEEDED

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    question = update.message.text.strip()
    chat_id = update.effective_chat.id

    if not question:
        return

    try:
        response = await groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": """

Classify the user's message into exactly one intent:
- create_monitor
- create_rain_monitor
- list_monitors
- cancel_monitor
- check_weather
- general

Return ONLY a valid JSON object with these keys:
intent, city, condition, threshold, monitor_id.

Rules:
- create_monitor requires a city, condition (below or above),
  and numeric temperature threshold.
- create_rain_monitor means the user wants an alert when rain is expected
  in a city, including requests about rain in the next few hours.
- For create_rain_monitor, provide the city and use null for
  condition, threshold, and monitor_id.
- cancel_monitor uses monitor_id if the user specifies an ID.
- list_monitors means show active monitoring tasks.
- check_weather means asking for weather in a city.
- If the request is ambiguous, use general.
- Never invent missing values. Use null for unknown values.
- threshold must be a number or null.
- monitor_id must be an integer or null.
- Do not execute actions. Only classify the request.

""",
                },
                {"role": "user", "content": question},
            ],
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty intent response")

        # Also tolerate JSON wrapped in Markdown code fences.
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3].strip()

        action = json.loads(content)

    except Exception as error:
        print("Intent detection error:", error)
        await answer_question(update, question)
        return

    intent = action.get("intent")


    # CREATE A RAIN MONITOR
    if intent == "create_rain_monitor":
        city = action.get("city")

        if not isinstance(city, str) or not city.strip():
            await update.message.reply_text(
                "Which city should I monitor for rain?\n\n"
                "Example: Alert me if rain is expected in Beirut "
                "in the next 2 hours."
            )
            return

        location = await asyncio.to_thread(
            get_coordinates, city.strip()
        )

        if location is None:
            await update.message.reply_text(
                f"I couldn't find the city '{city}'. "
                "Please try another city name."
            )
            return

        _, _, location_name = location

        monitor_id = await add_monitor(
            chat_id,
            location_name,
            "rain",
            0,
        )

        await update.message.reply_text(
            "🌧️ Rain monitor created successfully!\n\n"
            f"📍 City: {location_name}\n"
            "🌦️ I'll alert you if rain is expected "
            "in the next 2 hours.\n"
            "📊 Trigger: at least 50% rain probability "
            "and more than 0.1 mm precipitation.\n"
            f"🆔 Monitor ID: {monitor_id}\n\n"
            "I'll check the forecast in the background."
        )
        return

    # CREATE A WEATHER MONITOR
    if intent == "create_monitor":
        city = action.get("city")
        condition = action.get("condition")
        threshold = action.get("threshold")

        if (
            not isinstance(city, str)
            or not city.strip()
            or condition not in ("below", "above")
            or isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not -100 <= threshold <= 100
        ):
            await update.message.reply_text(
                "I understood that you want a weather monitor, "
                "but I need a city and a valid temperature condition.\n\n"
                "Example: Monitor Beirut below 20°C."
            )
            return

        location = await asyncio.to_thread(
            get_coordinates, city.strip()
        )

        if location is None:
            await update.message.reply_text(
                f"I couldn't find the city '{city}'. "
                "Please try another city name."
            )
            return

        _, _, location_name = location

        monitor_id = await add_monitor(
            chat_id,
            location_name,
            condition,
            float(threshold),
        )

        await update.message.reply_text(
            "✅ Monitor created successfully!\n\n"
            f"📍 City: {location_name}\n"
            f"🌡️ Alert when temperature is {condition} "
            f"{threshold}°C\n"
            f"🆔 Monitor ID: {monitor_id}\n\n"
            "I'll check the condition in the background."
        )
        return

    # LIST ACTIVE MONITORS
    if intent == "list_monitors":
        active = await get_active_monitors()
        mine = [
            item for item in active
            if str(item["chat_id"]) == str(chat_id)
        ]

        if not mine:
            await update.message.reply_text(
                "📋 You have no active monitors.\n"
                "Tell me what weather condition you want to monitor."
            )
            return

        lines = ["📋 Your Active Monitors\n"]

        for item in mine:
            lines.append(
                f"🆔 ID: {item['id']}\n"
                f"📍 City: {item['city']}\n"
                f"🌡️ {item['condition']} "
                f"{item['threshold']}°C\n"
            )

        await update.message.reply_text("\n".join(lines))
        return

    # CANCEL A MONITOR
    if intent == "cancel_monitor":
        monitor_id = action.get("monitor_id")

        if (
            isinstance(monitor_id, bool)
            or not isinstance(monitor_id, int)
        ):
            await update.message.reply_text(
                "Which monitor should I cancel?\n\n"
                "Use /monitors to see your monitor IDs, "
                "then say: Cancel monitor 3."
            )
            return

        active = await get_active_monitors()

        selected = next(
            (
                item for item in active
                if int(item["id"]) == monitor_id
                and str(item["chat_id"]) == str(chat_id)
            ),
            None,
        )

        if selected is None:
            await update.message.reply_text(
                "I couldn't find that active monitor in your chat. "
                "Use /monitors to see your active monitors."
            )
            return

        await deactivate_monitor(monitor_id)

        await update.message.reply_text(
            f"🛑 Monitor {monitor_id} cancelled.\n"
            f"📍 City: {selected['city']}"
        )
        return

    # CHECK WEATHER
    if intent == "check_weather":
        city = action.get("city")

        if not isinstance(city, str) or not city.strip():
            await update.message.reply_text(
                "Which city would you like the weather for?"
            )
            return

        try:
            location = await asyncio.to_thread(
                get_coordinates, city.strip()
            )

            if location is None:
                await update.message.reply_text(
                    "I couldn't find that city. Try another name."
                )
                return

            latitude, longitude, location_name = location

            data = await asyncio.to_thread(
                get_weather, latitude, longitude
            )

            temperature = data["current"]["temperature_2m"]
            wind = data["current"]["wind_speed_10m"]

            await update.message.reply_text(
                f"🌤️ Weather in {location_name}\n\n"
                f"🌡️ Temperature: {temperature}°C\n"
                f"💨 Wind: {wind} km/h"
            )

        except Exception as error:
            print("Natural-language weather error:", error)
            await update.message.reply_text(
                "Sorry, I couldn't retrieve the weather right now."
            )
        return

    # GENERAL QUESTIONS
    await answer_question(update, question)



# KEEP THE /ask COMMAND WORKING
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args)
    await answer_question(update, question)


# WEATHER LOCATION BUTTON
async def location_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    keyboard = [
        [KeyboardButton("📍 Share my location", request_location=True)]
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "Send me your location and I'll check the weather 🌤️",
        reply_markup=reply_markup,
    )


# HANDLE SHARED LOCATION
async def handle_location(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    location = update.message.location

    try:
        data = get_weather(location.latitude, location.longitude)

        temperature = data["current"]["temperature_2m"]
        wind = data["current"]["wind_speed_10m"]

        message = (
            "🌤️ Your Weather\n\n"
            f"📍 Coordinates: {location.latitude:.4f}, "
            f"{location.longitude:.4f}\n"
            f"🌡️ Temperature: {temperature}°C\n"
            f"💨 Wind: {wind} km/h"
        )

        await update.message.reply_text(message)

    except Exception as error:
        print("Location weather error:", error)
        await update.message.reply_text(
            "Sorry, I couldn't retrieve the weather right now."
        )

        
async def check_monitors(context: ContextTypes.DEFAULT_TYPE):
    monitors = await get_active_monitors()

    for monitor_item in monitors:
        try:
            # Find the city's coordinates.
            location = await asyncio.to_thread(
                get_coordinates,
                monitor_item["city"],
            )

            if location is None:
                print(
                    f"Could not find city: {monitor_item['city']}"
                )
                continue

            latitude, longitude, location_name = location


            # Handle rain monitors separately from temperature monitors.
            if monitor_item["condition"] == "rain":
                rain = await asyncio.to_thread(
                    get_rain_forecast,
                    latitude,
                    longitude,
                )

                print(
                    f"Rain monitor {monitor_item['id']}: "
                    f"{location_name}; "
                    f"rain expected = {rain['rain_expected']}"
                )

                if rain["rain_expected"]:
                    await context.bot.send_message(
                        chat_id=monitor_item["chat_id"],
                        text=(
                            "🌧️ Rain Alert!\n\n"
                            f"📍 City: {location_name}\n"
                            f"🌦️ Rain probability: "
                            f"{rain['probability']}%\n"
                            f"💧 Expected precipitation: "
                            f"{rain['precipitation']} mm\n"
                            f"🕒 Forecast time: {rain['time']}\n\n"
                            "Your rain monitor has been completed."
                        ),
                    )

                    await deactivate_monitor(monitor_item["id"])

                continue

            # Fetch the latest available weather.
            weather_data = await asyncio.to_thread(
                get_weather,
                latitude,
                longitude,
            )

            temperature = float(
                weather_data["current"]["temperature_2m"]
            )

            threshold = monitor_item["threshold"]
            condition = monitor_item["condition"]

            # Check whether the requested condition is met.
            condition_met = (
                condition == "below" and temperature < threshold
            ) or (
                condition == "above" and temperature > threshold
            )

            print(
                f"Monitor {monitor_item['id']}: "
                f"{location_name} = {temperature}°C; "
                f"condition met = {condition_met}"
            )

            if condition_met:
                await context.bot.send_message(
                    chat_id=monitor_item["chat_id"],
                    text=(
                        "🔔 Weather Alert!\n\n"
                        f"📍 City: {location_name}\n"
                        f"🌡️ Current temperature: {temperature}°C\n"
                        f"🎯 Your condition: {condition} "
                        f"{threshold}°C\n\n"
                        "Your monitor has been completed."
                    ),
                )

                await deactivate_monitor(monitor_item["id"])

        except Exception as error:
            print(
                f"Error checking monitor "
                f"{monitor_item['id']}: {error}"
            )



# WEATHER COMMAND
async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args)

    if not city:
        await update.message.reply_text(
            "Please give me a city.\n\nExample: /weather Beirut"
        )
        return

    try:
        location = get_coordinates(city)

        if location is None:
            await update.message.reply_text(
                "I couldn't find that location 😕"
            )
            return

        latitude, longitude, location_name = location
        data = get_weather(latitude, longitude)

        temperature = data["current"]["temperature_2m"]
        wind = data["current"]["wind_speed_10m"]

        message = (
            f"🌤️ Weather in {location_name}\n\n"
            f"🌡️ Temperature: {temperature}°C\n"
            f"💨 Wind: {wind} km/h"
        )

        await update.message.reply_text(message)

    except Exception as error:
        print("Weather error:", error)
        await update.message.reply_text(
            "Sorry, I couldn't retrieve the weather right now."
        )


# FIND CITY COORDINATES

def get_coordinates(city):
    url = "https://geocoding-api.open-meteo.com/v1/search"

    params = {
        "name": city.strip(),
        "count": 10,
        "language": "en",
        "format": "json",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    results = data.get("results", [])

    if not results:
        return None

    # Prefer an exact name match, ignoring capitalization.
    city_lower = city.strip().casefold()

    exact_matches = [
        place for place in results
        if place["name"].casefold() == city_lower
    ]

    if exact_matches:
        location = exact_matches[0]
    else:
        # Open-Meteo returns ranked global candidates.
        # Use its highest-ranked candidate as a fallback.
        location = results[0]

    return (
        location["latitude"],
        location["longitude"],
        location["name"],
    )



# GET CURRENT WEATHER
def get_weather(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,wind_speed_10m",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    return response.json()


def get_rain_forecast(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "precipitation_probability,precipitation",
        "forecast_days": 2,
        "timezone": "auto",
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()
    hourly = data.get("hourly", {})

    times = hourly.get("time", [])
    probabilities = hourly.get("precipitation_probability", [])
    precipitation = hourly.get("precipitation", [])

    if not times or not probabilities or not precipitation:
        raise ValueError("Rain forecast data is unavailable.")

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    timezone_name = data.get("timezone", "UTC")
    city_timezone = ZoneInfo(timezone_name)

    now = datetime.now(city_timezone)
    forecast_limit = now + timedelta(hours=2)

    for i, forecast_time in enumerate(times):
        forecast_datetime = datetime.fromisoformat(
    forecast_time
).replace(tzinfo=city_timezone)

        if now <= forecast_datetime <= forecast_limit:
            probability = probabilities[i]
            amount = precipitation[i]

            if probability is None or amount is None:
                continue

            if probability >= 50 and amount > 0.1:
                return {
                    "rain_expected": True,
                    "probability": probability,
                    "precipitation": amount,
                    "time": forecast_time,
                }

    return {
        "rain_expected": False,
        "probability": 0,
        "precipitation": 0,
        "time": None,
    }


# MAIN
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is missing from your .env file."
        )

    if not os.getenv("GROQ_API_KEY"):
        raise ValueError(
            "GROQ_API_KEY is missing from your .env file."
        )

    app = (
    Application.builder()
    .token(token)
    .post_init(post_init)
    .build()
)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("location", location_request))
    app.add_handler(CommandHandler("monitor", monitor))
    app.add_handler(CommandHandler("monitors", monitors))
    app.add_handler(CommandHandler("cancelmonitor", cancelmonitor))
    app.add_handler(
        MessageHandler(filters.LOCATION, handle_location)
    )

    # Keep this after the command handlers
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )
    app.job_queue.run_repeating(
    check_monitors,
    interval=300,
    first=5,
    name="weather_monitor_checker",
)

    print("Abed AI Agent is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
