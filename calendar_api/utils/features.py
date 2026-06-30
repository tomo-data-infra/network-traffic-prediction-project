#!/usr/bin/env python3
"""
features.py
- Network telemetry feature engineering framework.
- Aggregates high-frequency raw ping logs into stable machine learning matrices.
- Handles data gaps via imputation and maps time cyclically.
"""
import numpy as np
from math import sin, cos, pi
from datetime import datetime, timedelta

def add_time_features(agg_times, agg_features, one_hot=False):
    """
    Generate cyclical time features for each aggregated timestamp block.
    """
    feature_list = []
    for ts, feats in zip(agg_times, agg_features):
        dow = ts.weekday()           # 0 = Monday, 6 = Sunday
        wom = (ts.day - 1) // 7      # 0-based Week of Month (0-4)
        hour = ts.hour + ts.minute / 60.0

        if one_hot:
            dow_vec = np.eye(7)[dow]
            wom_vec = np.eye(5)[wom]
            vec = np.concatenate([
                [feats[0], feats[1], feats[2]], # [mean RTT, jitter, loss]
                dow_vec,
                wom_vec,
                [np.sin(2*np.pi*hour/24), np.cos(2*np.pi*hour/24)],
                [np.sin(2*np.pi*hour/12), np.cos(2*np.pi*hour/12)]
            ])
        else:
            vec = [
                feats[0],  # mean RTT
                feats[1],  # jitter
                feats[2],  # packet loss rate
                dow,
                wom,
                sin(2*np.pi*hour/24),
                cos(2*np.pi*hour/24),
                sin(2*np.pi*hour/12),
                cos(2*np.pi*hour/12)
            ]
        feature_list.append(vec)

    return np.array(feature_list)


def make_features(timestamps, rtts, timeouts, agg_seconds=60, tz=None, one_hot=False, start_window=None, end_window=None):
    """
    Aggregate raw RTT and timeout logs, impute tracking gaps, and map temporal attributes.
    Ensures calculations strictly respect requested time windows.
    """
    
    # Fallback logic if no timestamps provided
    if len(timestamps) == 0:
        if start_window and end_window:
            current = start_window.replace(second=0, microsecond=0)
            limit = end_window.replace(second=0, microsecond=0)
        else:
            return np.array([]), []
    else:
        current = start_window if start_window else timestamps[0].replace(second=0, microsecond=0)
        limit = end_window if end_window else timestamps[-1].replace(second=0, microsecond=0)

    delta = timedelta(seconds=agg_seconds)
    agg_features = []
    agg_times = []

    # Keep track of the last known good RTT for imputation
    last_valid_rtt = 3.0

    # Loop through the designated time window minute-by-minute
    while current < limit:
        # Create a mask for data points within this 60-second bin
        mask = (timestamps >= current) & (timestamps < current + delta)
        
        if not np.any(mask):
            # imputation logic
            # No data collected for this minute: Use stable imputation baseline
            # Imputation baseline for complete monitoring gaps (No pings attempted)
            mean_rtt = last_valid_rtt
            jitter = 0.0
            loss_rate = 0.0
        else:
            rtt_window = rtts[mask]
            timeout_window = timeouts[mask]

            # Loss rate calculation from timeout flags
            loss_rate = float(timeout_window.mean()) if len(timeout_window) > 0 else 0.0

            # Filter out NaNs / Timeouts for RTT metrics
            valid_rtts = rtt_window[~np.isnan(rtt_window)]
            
            if len(valid_rtts) > 0:
                mean_rtt = float(valid_rtts.mean())
                last_valid_rtt = mean_rtt  # Update baseline
                
                if len(valid_rtts) > 1:
                    # RFC 3550 style: Absolute difference between consecutive SUCCESSFUL packets
                    jitter = float(np.mean(np.abs(np.diff(valid_rtts))))
                else:
                    jitter = 0.0

            else:
                # 100% Packet Loss scenario within this active window
                # Set mean RTT to a maximum penalty value (e.g., 1000ms timeout) or last valid
                mean_rtt = 1000.0 
                jitter = 0.0 

        agg_features.append([mean_rtt, jitter, loss_rate])
        agg_times.append(current)
        current += delta

    agg_features_array = np.array(agg_features)
    agg_features_final = add_time_features(agg_times, agg_features_array, one_hot=one_hot)

    return agg_features_final, agg_times
