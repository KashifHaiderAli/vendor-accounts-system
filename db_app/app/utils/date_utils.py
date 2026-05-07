from datetime import date, datetime


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

