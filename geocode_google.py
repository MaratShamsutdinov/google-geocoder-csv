import os
import time
import requests
import urllib3
from pathlib import Path

# Отключаем предупреждения про verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === НАСТРОЙКИ ===
INPUT_CSV = "addresses.csv"               # исходные адреса (id,address)
OUTPUT_CSV = "addresses_geocoded.csv"     # сюда запишем результат
DELAY_SEC = 0.2                           # пауза между запросами

SESSION = requests.Session()
BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def load_api_key() -> str:
    """
    Берём ключ из переменной окружения GOOGLE_API_KEY
    или из файла google_api_key.txt (который в .gitignore).
    """
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if key:
        return key

    key_path = Path("google_api_key.txt")
    if key_path.exists():
        key = key_path.read_text(encoding="utf-8").strip()
        if key:
            return key

    raise SystemExit(
        "Google API key не найден. "
        "Задайте переменную окружения GOOGLE_API_KEY "
        "или создайте файл google_api_key.txt с ключом внутри."
    )


def geocode_once(addr: str):
    """Один запрос к Google. Возвращает (lat, lng, status)."""
    params = {
        "address": addr,
        "key": GOOGLE_API_KEY,
    }
    # verify=False из-за self-signed в цепочке
    resp = SESSION.get(BASE_URL, params=params, timeout=10, verify=False)
    resp.raise_for_status()
    data = resp.json()

    status = data.get("status", "UNKNOWN")
    if status != "OK":
        return None, None, status

    results = data.get("results", [])
    if not results:
        return None, None, status

    loc = results[0]["geometry"]["location"]
    return float(loc["lat"]), float(loc["lng"]), status


def geocode_with_trimming(addr: str):
    """
    Пытаемся геокодировать адрес, постепенно отрезая части по запятым справа.
    """
    # убираем пробелы и внешние кавычки, если есть
    original = addr.strip().strip('"')
    if not original:
        return None, None

    parts = [p.strip() for p in original.split(",") if p.strip()]
    if not parts:
        return None, None

    for n in range(len(parts), 0, -1):
        candidate = ", ".join(parts[:n])
        lat, lng, status = geocode_once(candidate)

        if status == "OK":
            if candidate != original:
                print(f"    [fallback] нашёл по укороченному адресу: {candidate!r}")
            return lat, lng

        print(f"    [try] {candidate!r} -> status={status}")

        if status not in ("ZERO_RESULTS", "OK"):
            break

    print(f"    [not found] ничего не нашли для {original!r}")
    return None, None


def parse_line(line: str):
    """
    Разбираем строку формата:
    id,address
    1,"Москва, ЦАО, ..."
    """
    line = line.strip()
    if not line:
        return None, None

    # пропускаем заголовок
    if line.lower().startswith("id,"):
        return None, None

    # делим по первой запятой: слева id, справа адрес
    parts = line.split(",", 1)
    if len(parts) < 2:
        return line.strip(), ""

    row_id = parts[0].strip()
    addr = parts[1].strip()

    # убираем внешние кавычки вокруг адреса
    if addr.startswith('"') and addr.endswith('"'):
        addr = addr[1:-1]

    # экселевские двойные кавычки внутри
    addr = addr.replace('""', '"')

    return row_id, addr


def main():
    in_path = Path(INPUT_CSV)
    out_path = Path(OUTPUT_CSV)

    if not in_path.exists():
        print(f"Файл {in_path} не найден")
        return

    # читаем входной файл как cp1251 (Excel по умолчанию)
    with in_path.open("r", encoding="cp1251", errors="replace") as f_in, \
     out_path.open("w", encoding="cp1251", newline="") as f_out:



        # пишем заголовок результата
        f_out.write("id,address,lat,lng\n")

        for line in f_in:
            row_id, addr = parse_line(line)

            if row_id is None and addr is None:
                continue

            if not addr:
                print(f"[{row_id}] пустой address, пропускаю")
                f_out.write(f'{row_id},"",,\n')
                f_out.flush()
                continue

            try:
                lat, lng = geocode_with_trimming(addr)
                print(f"[{row_id}] {addr} -> {lat}, {lng}")
            except Exception as e:
                print(f"[{row_id}] ERROR {addr}: {e}")
                lat, lng = None, None

            safe_addr = addr.replace('"', '""')
            lat_str = "" if lat is None else str(lat)
            lng_str = "" if lng is None else str(lng)

            f_out.write(f'{row_id},"{safe_addr}",{lat_str},{lng_str}\n')
            f_out.flush()

            time.sleep(DELAY_SEC)


if __name__ == "__main__":
    main()
