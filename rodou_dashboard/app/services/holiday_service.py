import calendar
from datetime import date, datetime, timedelta
from typing import List, Dict, Tuple

def get_easter_date(year: int) -> date:
    """Calcula a data do Domingo de Páscoa usando o algoritmo de Butcher (Computus)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

def get_national_holidays(year: int) -> Dict[date, str]:
    """
    Retorna o dicionário de feriados nacionais brasileiros (fixos e móveis)
    e datas sem circulação do Diário Oficial da União (DOU).
    """
    holidays: Dict[date, str] = {}

    # 1. Feriados Fixos Nacionais
    fixed = [
        ((1, 1), "Confraternização Universal"),
        ((4, 21), "Tiradentes"),
        ((5, 1), "Dia Mundial do Trabalho"),
        ((9, 7), "Independência do Brasil"),
        ((10, 12), "Nossa Senhora Aparecida"),
        ((11, 2), "Finados"),
        ((11, 15), "Proclamação da República"),
        ((11, 20), "Dia Nacional de Zumbi e da Consciência Negra"),
        ((12, 24), "Véspera de Natal (Sem DOU)"),
        ((12, 25), "Natal"),
        ((12, 31), "Véspera de Ano Novo (Sem DOU)"),
    ]
    for (m, d), name in fixed:
        try:
            holidays[date(year, m, d)] = name
        except ValueError:
            pass

    # 2. Feriados Móveis (baseados na Páscoa)
    pascoa = get_easter_date(year)
    holidays[pascoa - timedelta(days=48)] = "Carnaval (Segunda-feira)"
    holidays[pascoa - timedelta(days=47)] = "Carnaval (Terça-feira)"
    holidays[pascoa - timedelta(days=46)] = "Quarta-feira de Cinzas"
    holidays[pascoa - timedelta(days=2)] = "Sexta-feira Santa / Paixão de Cristo"
    holidays[pascoa] = "Domingo de Páscoa"
    holidays[pascoa + timedelta(days=60)] = "Corpus Christi"

    return holidays

def is_business_day(d: date) -> Tuple[bool, str]:
    """
    Verifica se uma data é dia útil para circulação do DOU.
    Retorna (is_business: bool, reason: str).
    """
    if d.weekday() >= 5:  # Sábado (5) ou Domingo (6)
        day_name = "Sábado" if d.weekday() == 5 else "Domingo"
        return False, f"Fim de semana ({day_name})"

    holidays = get_national_holidays(d.year)
    if d in holidays:
        return False, f"Feriado: {holidays[d]}"

    return True, "Dia útil"

def get_business_days_for_month(year: int, month: int, cap_today: bool = True) -> List[str]:
    """
    Retorna a lista de dias úteis com circulação do DOU para um determinado mês/ano,
    em ordem cronológica estrita ('YYYY-MM-DD').
    Desconsidera finais de semana e todos os feriados nacionais fixos e móveis.
    Se cap_today for True e for o mês corrente, limita até o dia de hoje.
    """
    last_day = calendar.monthrange(year, month)[1]
    today = date.today()
    if cap_today and year == today.year and month == today.month:
        last_day = min(last_day, today.day)

    business_days: List[str] = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        is_bus, _ = is_business_day(d)
        if is_bus:
            business_days.append(d.strftime('%Y-%m-%d'))

    return sorted(business_days)

def is_within_inlabs_retention_window(d_str: str, window_days: int = 120) -> bool:
    """
    Verifica se uma data 'YYYY-MM-DD' está dentro da janela de download do INLABS (últimos 120 dias).
    Datas anteriores a essa janela não estão mais disponíveis para download no portal INLABS.
    """
    try:
        dt = datetime.strptime(d_str, '%Y-%m-%d').date()
        min_inlabs_date = date.today() - timedelta(days=window_days)
        return dt >= min_inlabs_date
    except Exception:
        return False
