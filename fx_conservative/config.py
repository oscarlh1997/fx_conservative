# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import List, Dict, Optional
import yaml
import os

@dataclass
class Config:
    pairs: List[str]
    ema_fast: int
    ema_slow: int
    donchian_n: int
    adx_thresh: float
    rsi_len: int
    rsi_low: float
    rsi_high: float
    atr_stop_mult: float
    atr_trail_mult: float
    tp_R: float
    risk_per_trade: float
    total_risk_cap: float
    max_gross_leverage: float
    correl_window: int
    correl_threshold: float
    max_positions: int
    alignment_tz: str
    daily_alignment_hour: int
    log_dir: str
    state_path: str
    events_file: str
    spreads: Dict[str, float]
    carry_tilt: Dict[str, float]
    enable_event_blackout: bool

def load_config(path: str) -> Config:
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    return Config(
        pairs=cfg['pairs'],
        ema_fast=int(cfg['ema_fast']),
        ema_slow=int(cfg['ema_slow']),
        donchian_n=int(cfg['donchian_n']),
        adx_thresh=float(cfg['adx_thresh']),
        rsi_len=int(cfg['rsi_len']),
        rsi_low=float(cfg['rsi_low']),
        rsi_high=float(cfg['rsi_high']),
        atr_stop_mult=float(cfg['atr_stop_mult']),
        atr_trail_mult=float(cfg['atr_trail_mult']),
        tp_R=float(cfg['tp_R']),
        risk_per_trade=float(cfg['risk_per_trade']),
        total_risk_cap=float(cfg['total_risk_cap']),
        max_gross_leverage=float(cfg['max_gross_leverage']),
        correl_window=int(cfg['correl_window']),
        correl_threshold=float(cfg['correl_threshold']),
        max_positions=int(cfg['max_positions']),
        alignment_tz=str(cfg['alignment_tz']),
        daily_alignment_hour=int(cfg['daily_alignment_hour']),
        log_dir=str(cfg.get('log_dir','logs')),
        state_path=str(cfg.get('state_path','state/state.json')),
        events_file=str(cfg.get('events_file','config/events.csv')),
        spreads=dict(cfg.get('spreads',{})),
        carry_tilt=dict(cfg.get('carry_tilt',{})),
        enable_event_blackout=bool(cfg.get('enable_event_blackout', True)),
    )
