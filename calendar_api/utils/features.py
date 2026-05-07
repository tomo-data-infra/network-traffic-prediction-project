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

        # Time cyclic encoding
        hour_sin = sin(2 * pi * hour / 24)
        hour_cos = cos(2 * pi * hour / 24)

        if one_hot:
            dow_vec = np.eye(7)[dow]
            wom_vec = np.eye(5)[wom]
            vec = np.concatenate([
                [feats[0], feats[1], feats[2]], #loss
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


def make_features(timestamps, rtts, timeouts, agg_seconds=60, tz=None, one_hot=False):
    """
    Aggregate raw RTT and timeout data, remove outliers using IQR,
    compute packet loss, and generate time-based features.

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
    
    target_start = timestamps[0].replace(hour=9, minute=30, second=0, microsecond=0)
    target_end = timestamps[0].replace(hour=16, minute=30, second=0, microsecond=0)
    
    start_time = timestamps[0] + timedelta(minutes=1) #timestamps[0] +60 secs
    end_time = timestamps[-1] #timestamps[-1]

    # Round start_time down to nearest agg_seconds
    start_time = start_time.replace(second=0, microsecond=0)
    end_time = end_time.replace(second=0, microsecond=0)
    delta = timedelta(seconds=agg_seconds)

    agg_features = []
    agg_times = []

    current = target_start.replace(tzinfo=tz)
    #current = start_time
    while current <= target_end:
        mask = (timestamps >= current) & (timestamps < current + delta) #mask for 60 seconds 1D numpy.ndarray(True, True, True, True ... ] )
        if not np.any(mask):
            #!!!!!!!!!!! inputation logic !!!!!!!!!!!!!!
            mean_rtt = 5.5
            jitter = 2.1
            loss_rate = 0.0
            agg_features.append([mean_rtt, jitter, loss_rate])
            agg_times.append(current)
            
            current += delta
            continue

        rtt_window = rtts[mask]
        timeout_window = timeouts[mask]

        # Remove NaN values
        rtt_window = rtt_window[~np.isnan(rtt_window)]
        
        # Remove outliners with 3σ
        if len(rtt_window) > 0:
            rtt_mean = rtt_window.mean()
            rtt_std = rtt_window.std()
            lower_bound = rtt_mean - 3 * rtt_std
            upper_bound = rtt_mean + 3 * rtt_std
            valid_rtt = rtt_window[(rtt_window > lower_bound) & (rtt_window < upper_bound)]
            
        else:
            valid_rtt = np.array([])
        
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

        mean_rtt = valid_rtt.mean() if len(valid_rtt) > 0 else 0.0 # potential stable baseline
        jitter = valid_rtt.std() if len(valid_rtt) > 0 else 0.0
        #Count non-timeouts (0's)
        #num_non_timeouts = np.sum(timeout_window == 0)
        #loss_rate = (agg_seconds - num_non_timeouts)/ agg_seconds if len(timeout_window) > 0 else 0.0
        loss_rate = timeout_window.mean() if len(timeout_window) > 0 else 0.0

        agg_features.append([mean_rtt, jitter, loss_rate])
        agg_times.append(current)

        current += delta

    agg_features = np.array(agg_features)
    # loss_rates = np.array([timeouts[(timestamps >= t) & (timestamps < t + delta)].mean() 
    #                        for t in agg_times])

    agg_features_final = add_time_features(agg_times, agg_features, one_hot=one_hot) # loss_rates,

    return agg_features_final, agg_times

