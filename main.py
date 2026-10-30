import os
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, cast

import requests
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import TypedDict

class WeatherRecord(TypedDict):
    city: str
    temperature: float
    wind_speed: float
    time: str
    fetched_at: str

@dataclass(frozen=True)
class Config:
    latitude: float
    longitude: float
    city_name: str
    output_file: str



WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10

def load_config() -> Config:
    """Читає налаштування з .env та перевіряє їх."""
    load_dotenv()
    required = ("LATITUDE", "LONGITUDE", "CITY_NAME", "OUTPUT_FILE")
    values = {key: os.getenv(key) for key in required}

    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError(f"Не задано в .env: {', '.join(missing)}")

    try:
        latitude = float(values["LATITUDE"])      # type: ignore[arg-type]
        longitude = float(values["LONGITUDE"])    # type: ignore[arg-type]
    except ValueError as e:
        raise ValueError("LATITUDE і LONGITUDE мають бути числами") from e

    return Config(
        latitude=latitude,
        longitude=longitude,
        city_name=values["CITY_NAME"],            # type: ignore[arg-type]
        output_file=values["OUTPUT_FILE"],        # type: ignore[arg-type]
    )

def fetch_weather_data(latitude: float, longitude: float) -> dict[str, Any]:
    """Запитує поточні погодні дані для координат."""
    response = requests.get(
        WEATHER_API_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data: Any = response.json()
    if not isinstance(data, dict):
        raise ValueError("Weather API response must be a JSON object")
    return cast(dict[str, Any], data)


def parse_weather(raw: dict[str, object], city: str) -> WeatherRecord:
    """Перетворює відповідь API на запис про погоду."""
    current = raw.get("current")
    if not isinstance(current, dict):
        raise ValueError("Weather API response must contain 'current' as a JSON object")
    current_data = cast(dict[str, object], current)

    temperature = current_data.get("temperature_2m")
    wind_speed = current_data.get("wind_speed_10m")
    time = current_data.get("time")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise ValueError("Weather API response must contain a numeric temperature_2m")
    if not isinstance(wind_speed, (int, float)) or isinstance(wind_speed, bool):
        raise ValueError("Weather API response must contain a numeric wind_speed_10m")
    if not isinstance(time, str) or not time:
        raise ValueError("Weather API response must contain a non-empty time")

    return {
        "city": city,
        "temperature": temperature,
        "wind_speed": wind_speed,
        "time": time,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def save_to_file(record: WeatherRecord, path: str | Path) -> None:
    """Додає запис у JSON-файл зі списком записів."""
    output_path = Path(path)
    records: list[WeatherRecord] = []

    if output_path.exists():
        text = output_path.read_text(encoding="utf-8").strip()
        if text:  # порожній файл або тільки пробіли/переноси → лишаємо []
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Файл {output_path} пошкоджений: {e}") from e
            if not isinstance(loaded, list):
                raise ValueError(f"Очікувався список у {output_path}")
            records = cast(list[WeatherRecord], loaded)

    records.append(record)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    """Отримує, зберігає та виводить дані про погоду."""
    try:
        config = load_config()
        raw = fetch_weather_data(config.latitude, config.longitude)
        weather = parse_weather(raw, config.city_name)
        save_to_file(weather, config.output_file)
    except requests.exceptions.Timeout:
        print("Помилка: сервер не відповів вчасно")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("Помилка: немає з'єднання з інтернетом")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Помилка API: {e}")
        sys.exit(1)
    except (ValueError, OSError) as e:
        print(f"Помилка: {e}")
        sys.exit(1)

    print(json.dumps(weather, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()