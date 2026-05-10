#!/usr/bin/env python3
import numpy as np
from math import sin, cos, pi
from datetime import datetime, timedelta

def add_time_features(agg_times, agg_features, one_hot=False): # loss_rates, #used in make_features
    """
    Generate feature vectors for each aggregated timestamp.

    Parameters
    ----------
    agg_times : list of datetime
        List of timestamps (one per aggregation bin).
    agg_features : np.ndarray
        Array of shape (n, 3) with [mean RTT, jitter, loss_rate].
    # loss_rates : list or np.ndarray
    #     Loss rate per bin (between 0 and 1).
    one_hot : bool, optional
        If True, use one-hot encoding for weekday (7-dim) and week-of-month (5-dim).
        If False, use integer values.

    Returns
    -------
    np.ndarray
        Features for each timestamp.
        - If one_hot=False: shape (n, 7) = [mean RTT, jitter, loss, dow, wom, hour_sin, hour_cos]
        - If one_hot=True : shape (n, 2+1+7+5+2) = (n,17)
    """
    feature_list = []
    for ts, feats in zip(agg_times, agg_features): #, loss , loss_rates
        # Weekday / week-of-month
        dow = ts.weekday()           # 0=Mon
        wom = (ts.day - 1) // 7      # 0-based index (0-4)
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
                feats[2],  # packet loss rate loss,
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
    Aggregate raw RTT and timeout data, remove outliers, and generate time features.
    Strictly follows the start_window and end_window provided.

    Parameters
    ----------
    timestamps : np.ndarray of datetime
    rtts : np.ndarray of RTT values (ms)
    timeouts : np.ndarray of 0/1 indicating timeout
    agg_seconds : int, aggregation interval in seconds
    tz : timezone, optional
    one_hot : bool, if True, use one-hot encoding for weekday/week-of-month

    Returns
    -------
    features : np.ndarray of shape (n_bins, n_features)
    agg_times : list of datetime, center of each aggregation bin
    """
    
    # Fallback logic if no timestamps provided
    if len(timestamps) == 0:
        if start_window and end_window:
            # Generate imputed data for the entire requested window
            current = start_window.replace(second=0, microsecond=0)
            limit = end_window.replace(second=0, microsecond=0)
        else:
            return np.array([]), []
    else:
        # Determine the boundaries based on the window or the data
        current = start_window if start_window else timestamps[0].replace(second=0, microsecond=0)
        limit = end_window if end_window else timestamps[-1].replace(second=0, microsecond=0)

    delta = timedelta(seconds=agg_seconds)
    agg_features = []
    agg_times = []

    # Loop through the designated time window minute-by-minute
    while current <= limit:
        # Create a mask for data points within this 60-second bin
        mask = (timestamps >= current) & (timestamps < current + delta) #mask for 60 seconds 1D numpy.ndarray(True, True, True, True ... ] )
        
        if not np.any(mask):
            #!!!!!!!!!!! inputation logic !!!!!!!!!!!!!!
            # No data collected for this minute: Use stable imputation baseline
            mean_rtt = 5.5
            jitter = 2.1
            loss_rate = 0.0
        else:
            rtt_window = rtts[mask]
            timeout_window = timeouts[mask]

            # Remove NaN values from RTT window
            rtt_window = rtt_window[~np.isnan(rtt_window)]
            
            if len(rtt_window) > 0:
                # 3-Sigma Outlier Removal
                #         # Outlier removal using IQR
                #         if len(rtt_window) > 0:
                #             q1 = np.percentile(rtt_window, 25)
                #             q3 = np.percentile(rtt_window, 75)
                #             iqr = q3 - q1
                #             lower_bound = q1 - 3.0 * iqr    #1.5
                #             upper_bound = q3 + 3.0 * iqr    #1.5
                #             valid_rtt = rtt_window[(rtt_window >= lower_bound) & (rtt_window <= upper_bound)]
                #         else:
                #             valid_rtt = np.array([])
                rtt_mean_val = rtt_window.mean()
                rtt_std_val = rtt_window.std()
                lower_bound = rtt_mean_val - 3 * rtt_std_val
                upper_bound = rtt_mean_val + 3 * rtt_std_val
                
                valid_rtt = rtt_window[(rtt_window > lower_bound) & (rtt_window < upper_bound)]
                
                # Final Stats for the bin
                mean_rtt = valid_rtt.mean() if len(valid_rtt) > 0 else 5.5
                jitter = valid_rtt.std() if len(valid_rtt) > 0 else 2.1
            else:
                mean_rtt = 5.5
                jitter = 2.1
            
            # Loss rate calculation from timeout flags
            loss_rate = timeout_window.mean() if len(timeout_window) > 0 else 0.0

        agg_features.append([mean_rtt, jitter, loss_rate])
        agg_times.append(current)
        
        # Advance to the next aggregation bin
        current += delta

    # Convert results to arrays and add time features (sin/cos encoding)
    agg_features_array = np.array(agg_features)
    agg_features_final = add_time_features(agg_times, agg_features_array, one_hot=one_hot)

    return agg_features_final, agg_times
