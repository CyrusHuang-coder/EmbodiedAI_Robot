def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))

def lerp(a, b, alpha):
    return a * (1 - alpha) + b * alpha