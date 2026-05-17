from utils.math_utils import clamp, lerp

class MotionFilter:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.value = 0

    def update(self, target):
        self.value = lerp(self.value, target, self.alpha)
        return self.value