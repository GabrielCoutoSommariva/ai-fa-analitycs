import re


BLOCKED = re.compile(r"\b(insert|update|delete|drop|alter|create|copy|truncate|grant|revoke|vacuum|analyze)\b", re.I)
PARAM = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


def is_safe_select(sql: str) -> bool:
    cleaned = sql.strip().rstrip(";")
    if not cleaned.lower().startswith("select"):
        return False
    if BLOCKED.search(cleaned):
        return False
    if ";" in cleaned:
        return False
    return " analytics." in f" {cleaned.lower()}" or " from analytics" in cleaned.lower()


def template_to_psycopg(sql_template: str) -> str:
    cleaned = sql_template.strip().rstrip(";")
    return PARAM.sub(lambda match: f"%({match.group(1)})s", cleaned)
