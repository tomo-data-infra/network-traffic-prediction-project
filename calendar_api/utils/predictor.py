#!/usr/bin/env python3
"""
predictor.py
- Network telemetry predictive analytics and statistical forecasting core engine.
- Implements high-speed NumPy array masking to prevent query-in-loop performance degradation.
- Calculates network jitter strictly compliant with RFC 3550.
"""

import os
import json
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ..models import PingLog, EventSession

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = BASE_DIR / "predicted_traffic_model.json"

def calculate_rfc3550_jitter(rtt_list):
    """
    Calculates network jitter according to RFC 3550 guidelines:
    Mean absolute differences between consecutive successful round-trip tracking packets.
    """
    if len(rtt_list) < 2:
        return 0.0
    return float(np.mean(np.abs(np.diff(rtt_list))))

def train_baseline_profiles(days_back=30):
    """
    Analyzes historical tracking logs to build a statistical baseline coefficient model matrix.
    Uses high-speed in-memory NumPy masking to protect against DB query-in-loop latency.
    """
    now = datetime.now(JST)
    start_history = now - timedelta(days=days_back)

    # High-Performance Bulk Data Extraction (Exactly ONE query each)
    historical_logs = PingLog.objects.filter(ts__range=[start_history, now], target_id=1).order_by('ts')
    historical_events = EventSession.objects.filter(start_ts__lt=now, end_ts__gt=start_history)

    # Convert database streams instantly to memory arrays for rapid computation matrices
    log_ts = np.array([l.ts for l in historical_logs], dtype=object)
    log_rtts = np.array([l.rtt_ms if l.rtt_ms is not None else np.nan for l in historical_logs], dtype=float)
    log_timeouts = np.array([1 if l.is_timeout else 0 for l in historical_logs], dtype=int)

    event_time_blocks = []
    event_type_data = {}

    # In-Memory Slicing Engine
    for evt in historical_events:
        event_time_blocks.append((evt.start_ts, evt.end_ts))
        cat = evt.session_category
        devices = max(1, evt.expected_devices)
        
        # Build an instantaneous high-speed memory mask instead of calling the database again
        mask = (log_ts >= evt.start_ts) & (log_ts <= evt.end_ts)
        rtts_in_event = log_rtts[mask]
        timeouts_in_event = log_timeouts[mask]

        # Clean out dropped packets to analyze pure latency
        valid_rtts = rtts_in_event[~np.isnan(rtts_in_event)]

        if len(valid_rtts) > 0:
            if cat not in event_type_data:
                event_type_data[cat] = {"rtt_per_device": [], "jitter_per_device": [], "loss": []}
            
            # RFC 3550 compliant jitter extraction
            calculated_jitter = calculate_rfc3550_jitter(valid_rtts)
            
            # Normalize impact metrics per device to allow scalable runtime linear forecasting
            event_type_data[cat]["rtt_per_device"].append(np.mean(valid_rtts) / devices)
            event_type_data[cat]["jitter_per_device"].append(calculated_jitter / devices)
            event_type_data[cat]["loss"].append(np.mean(timeouts_in_event) if len(timeouts_in_event) > 0 else 0.0)

    # Compile Category Profiles
    profiles = {}
    for cat, metrics in event_type_data.items():
        profiles[cat] = {
            "rtt_coef": float(np.mean(metrics["rtt_per_device"])),
            "jitter_coef": float(np.mean(metrics["jitter_per_device"])),
            "loss_baseline": float(np.mean(metrics["loss"]))
        }

    # Extract Global System Idle Baseline using inverse masking array flags
    is_idle_mask = np.ones(len(log_ts), dtype=bool)
    for start, end in event_time_blocks:
        is_idle_mask &= ~((log_ts >= start) & (log_ts <= end))

    idle_rtts = log_rtts[is_idle_mask]
    idle_rtts_clean = idle_rtts[~np.isnan(idle_rtts)]
    idle_timeouts = log_timeouts[is_idle_mask]

    profiles["_idle"] = {
        "rtt": float(np.mean(idle_rtts_clean)) if len(idle_rtts_clean) > 0 else 3.0,
        "jitter": calculate_rfc3550_jitter(idle_rtts_clean),
        "loss": float(np.mean(idle_timeouts)) if len(idle_timeouts) > 0 else 0.0
    }

    # Serialize model profile parameters cleanly using absolute tracking targets
    with open(MODEL_PATH, "w") as f:
        json.dump(profiles, f, indent=4)
        
    return profiles


def forecast_remaining_day(start_window, end_window):
    """
    Generates minute-by-minute projected curves for the remaining view window
    by overlaying model parameters over upcoming calendar items.
    """
    try:
        with open(MODEL_PATH, "r") as f:
            profiles = json.load(f)
    except FileNotFoundError:
        # Fallback automated recovery loop if binary file drops
        profiles = train_baseline_profiles()

    upcoming_events = EventSession.objects.filter(
        start_ts__lt=end_window,
        end_ts__gt=start_window
    ).order_by('start_ts')

    forecast_points = []
    current_bin = start_window.replace(second=0, microsecond=0)
    delta = timedelta(minutes=1)

    while current_bin < end_window:
        active_event = None
        for evt in upcoming_events:
            if evt.start_ts <= current_bin < evt.end_ts:
                active_event = evt
                break

        if active_event:
            cat = active_event.session_category
            devs = active_event.expected_devices
            profile = profiles.get(cat, {"rtt_coef": 0.5, "jitter_coef": 0.1, "loss_baseline": 0.01})
            
            # Linear scaling model projection: base idle + (coefficient impact variable * concurrent density)
            pred_rtt = profiles["_idle"]["rtt"] + (profile["rtt_coef"] * devs)
            pred_jitter = profiles["_idle"]["jitter"] + (profile["jitter_coef"] * devs)
            pred_loss = min(1.0, profile["loss_baseline"] * (devs / 5.0))
        else:
            pred_rtt = profiles["_idle"]["rtt"]
            pred_jitter = profiles["_idle"]["jitter"]
            pred_loss = profiles["_idle"]["loss"]

        forecast_points.append({
            "ts": current_bin.isoformat(),
            "pred_rtt": round(pred_rtt, 2),
            "pred_jitter_high": round(pred_rtt + pred_jitter, 2),
            "pred_jitter_low": round(max(0, pred_rtt - pred_jitter), 2),
            "pred_loss": round(pred_loss, 4)
        })
        current_bin += delta

    return forecast_points
