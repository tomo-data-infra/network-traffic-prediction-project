#!/usr/bin/env python3
import numpy as np
from datetime import datetime, timedelta, timezone
from django.db.models import Avg, StdDev
from ..models import PingLog, EventSession

JST = timezone(timedelta(hours=9))

def train_baseline_profiles(days_back=30):
    """
    Analyzes the last 30 days of telemetry to build a statistical baseline matrix
    decoupled by event types and baseline idle states.
    """
    now = datetime.now(JST)
    start_history = now - timedelta(days=days_back)

    # 1. Fetch historical windows
    historical_logs = PingLog.objects.filter(ts__range=[start_history, now], target_id=1)
    historical_events = EventSession.objects.filter(start_ts__lt=now, end_ts__gt=start_history)

    # 2. Build explicit masks for times when events were running vs idle times
    event_time_blocks = []
    event_type_data = {}

    for evt in historical_events:
        event_time_blocks.append((evt.start_ts, evt.end_ts))
        cat = evt.session_category
        devices = max(1, evt.expected_devices)
        
        # Pull log slices inside this specific event window
        logs_in_evt = historical_logs.filter(ts__range=[evt.start_ts, evt.end_ts])
        rtts = [l.rtt_ms for l in logs_in_evt if l.rtt_ms is not None]
        timeouts = [1 if l.is_timeout else 0 for l in logs_in_evt]

        if len(rtts) > 0:
            if cat not in event_type_data:
                event_type_data[cat] = {"rtt_per_device": [], "jitter_per_device": [], "loss": []}
            
            # Normalize RTT impact per connected device to scale linearly later
            event_type_data[cat]["rtt_per_device"].append(np.mean(rtts) / devices)
            event_type_data[cat]["jitter_per_device"].append(np.std(rtts) / devices)
            event_type_data[cat]["loss"].append(np.mean(timeouts))

    # 3. Compute Averages per Category Profile
    profiles = {}
    for cat, metrics in event_type_data.items():
        profiles[cat] = {
            "rtt_coef": float(np.mean(metrics["rtt_per_device"])),
            "jitter_coef": float(np.mean(metrics["jitter_per_device"])),
            "loss_baseline": float(np.mean(metrics["loss"]))
        }

    # 4. Calculate System Idle Baseline (where no events were running)
    idle_logs = historical_logs
    for start, end in event_time_blocks:
        idle_logs = idle_logs.exclude(ts__range=[start, end])

    idle_rtts = [l.rtt_ms for l in idle_logs if l.rtt_ms is not None]
    idle_timeouts = [1 if l.is_timeout else 0 for l in idle_logs]

    profiles["_idle"] = {
        "rtt": float(np.mean(idle_rtts)) if idle_rtts else 3.0,
        "jitter": float(np.std(idle_rtts)) if idle_rtts else 0.5,
        "loss": float(np.mean(idle_timeouts)) if idle_timeouts else 0.0
    }

    # Save to a local json file to act as the saved model binary
    with open("predicted_traffic_model.json", "w") as f:
        import json
        json.dump(profiles, f)
        
    return profiles


def forecast_remaining_day(start_window, end_window):
    """
    Generates minute-by-minute projected curves for the remaining view window
    by overlaying model parameters over upcoming calendar items.
    """
    # Load model profile parameters
    try:
        with open("predicted_traffic_model.json", "r") as f:
            import json
            profiles = json.load(f)
    except FileNotFoundError:
        # Auto-train baseline if model missing
        profiles = train_baseline_profiles()

    # Fetch future events within the visible chart window
    upcoming_events = EventSession.objects.filter(
        start_ts__lt=end_window,
        end_ts__gt=start_window
    ).order_by('start_ts')

    forecast_points = []
    current_bin = start_window.replace(second=0, microsecond=0)
    delta = timedelta(minutes=1)

    while current_bin < end_window:
        # Check if an event overlaps this specific 1-minute bin
        active_event = None
        for evt in upcoming_events:
            if evt.start_ts <= current_bin < evt.end_ts:
                active_event = evt
                break

        if active_event:
            cat = active_event.session_category
            devs = active_event.expected_devices
            profile = profiles.get(cat, {"rtt_coef": 0.5, "jitter_coef": 0.1, "loss_baseline": 0.01})
            
            # Linear scaling model: base idle latency + (impact coefficient * device density)
            pred_rtt = profiles["_idle"]["rtt"] + (profile["rtt_coef"] * devs)
            pred_jitter = profiles["_idle"]["jitter"] + (profile["jitter_coef"] * devs)
            pred_loss = min(1.0, profile["loss_baseline"] * (devs / 5.0))
        else:
            # Flattened system default state
            pred_rtt = profiles["_idle"]["rtt"]
            pred_jitter = profiles["_idle"]["jitter"]
            box_loss = profiles["_idle"]["loss"]
            pred_loss = box_loss

        forecast_points.append({
            "ts": current_bin.isoformat(),
            "pred_rtt": round(pred_rtt, 2),
            "pred_jitter_high": round(pred_rtt + pred_jitter, 2),
            "pred_jitter_low": round(max(0, pred_rtt - pred_jitter), 2),
            "pred_loss": round(pred_loss, 4)
        })
        current_bin += delta

    return forecast_points
