# -*- coding: utf-8 -*-
from dateutil import tz
import datetime as dt

def next_daily_close_eu_madrid(alignment_hour: int = 17):
    ny = tz.gettz("America/New_York")
    mad = tz.gettz("Europe/Madrid")
    now_mad = dt.datetime.now(tz=mad)
    now_ny = now_mad.astimezone(ny)

    base_date = now_ny.date()
    if now_ny.hour >= alignment_hour:
        base_date = (now_ny + dt.timedelta(days=1)).date()

    close_ny = dt.datetime.combine(base_date, dt.time(hour=alignment_hour, minute=0, second=0, tzinfo=ny))
    return close_ny.astimezone(mad)

def parse_any_ts(ts_str: str):
    """Intenta parsear timestamp ISO con o sin tz; si no trae tz, asume Europe/Madrid."""
    from dateutil import parser
    import pytz
    dt_obj = parser.parse(ts_str)
    if dt_obj.tzinfo is None:
        dt_obj = pytz.timezone('Europe/Madrid').localize(dt_obj)
    return dt_obj
