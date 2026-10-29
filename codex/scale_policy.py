"""User-selected character scale; keep the upstream bubble size independent."""
import math

MIN_SCALE = 0.01
MAX_SCALE = 1.0
SCALE_STEP = 0.01


def normalize_saved_scale(value):
    if type(value) in (int, float) and math.isfinite(value):
        return min(MAX_SCALE, max(MIN_SCALE, value))
    return value


def adapt_client_scale(source):
    return source.replace('min: 0.55, max: 1.4, step: 0.05',
                          f'min: {MIN_SCALE}, max: {MAX_SCALE}, step: {SCALE_STEP}')


def adapt_native_scale(source):
    for operand in ('scale', 'd', 'Double(i)', 'value'):
        source = source.replace(f'min(1.4, max(0.55, {operand}))',
                                f'min({MAX_SCALE}, max({MIN_SCALE}, {operand}))')
    source = source.replace('[("迷你", 0.6), ("小", 0.8), ("标准", 1.0), ("大", 1.25)]',
                            '[("迷你", 0.1), ("小", 0.25), ("中", 0.5), ("大", 0.75), ("标准", 1.0)]')
    return source.replace('abs(scale - value) < 0.05', 'abs(scale - value) < 0.005')
