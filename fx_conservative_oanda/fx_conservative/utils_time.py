# -*- coding: utf-8 -*-
"""
Utilidades de tiempo para el scheduler y parseo de timestamps.
Adaptado para US equities con cierre NYSE a las 16:00 ET.
"""
from dateutil import tz
import datetime as dt
import pandas as pd


def next_daily_close_eu_madrid(alignment_hour: int = 16):
    """
    Calcula el próximo cierre diario del mercado de US equities (NYSE 16:00 ET)
    expresado en hora de Madrid/España.

    Args:
        alignment_hour: Hora de cierre en ET (default 16 = 16:00 ET / NYSE close).

    Returns:
        datetime con timezone Europe/Madrid del próximo cierre.
    """
    ny = tz.gettz("America/New_York")
    mad = tz.gettz("Europe/Madrid")
    now_mad = dt.datetime.now(tz=mad)
    now_ny = now_mad.astimezone(ny)

    base_date = now_ny.date()
    # Si ya pasó la hora de cierre en NY hoy, apuntar al siguiente día hábil
    if now_ny.hour > alignment_hour or (now_ny.hour == alignment_hour and now_ny.minute >= 5):
        base_date = (now_ny + dt.timedelta(days=1)).date()

    # Saltar fines de semana (NYSE cierra sábado y domingo)
    while base_date.weekday() >= 5:  # 5=Sat, 6=Sun
        base_date += dt.timedelta(days=1)

    close_ny = dt.datetime.combine(
        base_date,
        dt.time(hour=alignment_hour, minute=5, second=0, tzinfo=ny)
    )
    return close_ny.astimezone(mad)


def parse_any_ts(ts_str: str) -> pd.Timestamp:
    """
    Parsea un timestamp ISO con o sin zona horaria.
    Si no tiene tz, asume UTC.

    Returns:
        pd.Timestamp timezone-aware (UTC).
    """
    try:
        ts = pd.to_datetime(ts_str, utc=True)
        return ts
    except Exception:
        pass
    # Fallback: use dateutil parser
    from dateutil import parser as dtparser
    dt_obj = dtparser.parse(ts_str)
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
    return pd.Timestamp(dt_obj).tz_convert("UTC")
