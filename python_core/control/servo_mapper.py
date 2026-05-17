class ServoMapper:
    """
    舵机角度映射工具类
    将手势识别得到的归一化参数转换为实际舵机角度 (0~180)。
    """
    def __init__(self):
        pass
    @staticmethod
    def map_grip(pinch_ratio):
        """
        将捏合比值映射为夹爪角度。
        :param pinch_ratio: 拇指与食指距离 / 手掌尺寸 (0~1+)
        :return: 夹爪角度 (0~90)，对应实际机械安全范围
        """
        return int(max(0, min(90, (pinch_ratio - 0.12) * 260)))