import math

import numpy as np

from engine.parser import DIFFICULTY_ORDER


def build_aps_quantile_bands(aps_values, labels=DIFFICULTY_ORDER):
    clean = []
    for value in aps_values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            clean.append(numeric)
    if not clean:
        return {}

    ordered = sorted(clean)
    quantiles = np.linspace(0.0, 1.0, len(labels) + 1)
    edges = [float(np.quantile(ordered, quantile)) for quantile in quantiles]

    for index in range(1, len(edges)):
        if edges[index] < edges[index - 1]:
            edges[index] = edges[index - 1]

    bands = {}
    for index, label in enumerate(labels):
        bands[label] = {
            "min": edges[index],
            "max": edges[index + 1],
        }
    return bands


def classify_aps_bracket(aps_value, bands, labels=DIFFICULTY_ORDER):
    try:
        numeric = float(aps_value)
    except (TypeError, ValueError):
        return labels[0]

    if not math.isfinite(numeric) or not bands:
        return labels[0]

    for index, label in enumerate(labels):
        band = bands.get(label)
        if not band:
            continue
        upper = band["max"]
        if index == len(labels) - 1 or numeric <= upper:
            return label

    return labels[-1]


def format_band_label(low, high, open_ended=False):
    if low is None:
        return "APS unavailable"
    if open_ended or high is None:
        return f"{float(low):.2f}+ APS"
    return f"{float(low):.2f}\u2013{float(high):.2f} APS"
