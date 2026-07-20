from calendar import monthrange
from datetime import date, timedelta
import re


MONTHS = {
    "janeiro": 1,
    "jan": 1,
    "fevereiro": 2,
    "fev": 2,
    "marco": 3,
    "março": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "maio": 5,
    "mai": 5,
    "junho": 6,
    "jun": 6,
    "julho": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "setembro": 9,
    "set": 9,
    "outubro": 10,
    "out": 10,
    "novembro": 11,
    "nov": 11,
    "dezembro": 12,
    "dez": 12,
}


def parse_period(question: str, data_inicio: date | None, data_fim: date | None) -> dict:
    normalized = question.lower()
    today = date.today()

    if re.search(r"\bontem\b", normalized):
        target = today - timedelta(days=1)
        return {"data": target, "data_inicio": target, "data_fim": target}

    if re.search(r"\bhoje\b", normalized):
        return {"data": today, "data_inicio": today, "data_fim": today}

    for month_name, month in MONTHS.items():
        pattern = rf"\b{month_name}\b(?:\s+de)?\s+(20\d{{2}})"
        match = re.search(pattern, normalized)
        if match:
            year = int(match.group(1))
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            return {"data": start, "data_inicio": start, "data_fim": end}

    iso_date = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", normalized)
    if iso_date:
        target = date(int(iso_date.group(1)), int(iso_date.group(2)), int(iso_date.group(3)))
        return {"data": target, "data_inicio": target, "data_fim": target}

    if data_inicio and data_fim:
        return {"data": data_inicio, "data_inicio": data_inicio, "data_fim": data_fim}

    if data_inicio:
        return {"data": data_inicio, "data_inicio": data_inicio, "data_fim": data_inicio}

    return {"data": None, "data_inicio": None, "data_fim": None}
