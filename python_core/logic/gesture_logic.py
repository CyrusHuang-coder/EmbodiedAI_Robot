import math
from config.params import Params

class GestureLogic:
    """
    手势逻辑封装类，使用 Params 统一管理阈值。
    """
    def __init__(self):
        pass
    # ---------- 手指姿态判断 ----------
    @staticmethod
    def finger_up(hand_lms, tip_idx, pip_idx):
        """指尖是否明显高于 PIP 关节（伸直）"""
        return hand_lms[tip_idx].y < hand_lms[pip_idx].y - Params.FINGER_UP_TOLERANCE

    @staticmethod
    def finger_bent(hand_lms, tip_idx, pip_idx):
        """指尖是否明显低于 PIP 关节（弯曲）"""
        return hand_lms[tip_idx].y > hand_lms[pip_idx].y + Params.FINGER_BENT_TOLERANCE

    @staticmethod
    def get_palm_size(hand_lms):
        """估算手掌尺寸（手腕到中指 MCP）用于归一化"""
        wrist = hand_lms[0]
        middle_mcp = hand_lms[9]
        return math.hypot(wrist.x - middle_mcp.x, wrist.y - middle_mcp.y) + 1e-6

    @classmethod
    def get_pinch_ratio(cls, hand_lms):
        """拇食指距离相对于手掌尺寸的比值"""
        thumb_tip = hand_lms[4]
        index_tip = hand_lms[8]
        dist = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
        return dist / cls.get_palm_size(hand_lms)

    # ---------- 手势分类（带迟滞） ----------
    @classmethod
    def classify_gesture(cls, hand_lms, current_active):
        """
        返回手势字符串：'open_palm' / 'fist' / 'pinch' / 'v_sign' / 'point' / None
        current_active 用于 pinch 迟滞判断
        """
        index_up = cls.finger_up(hand_lms, 8, 6)
        middle_up = cls.finger_up(hand_lms, 12, 10)
        ring_up = cls.finger_up(hand_lms, 16, 14)
        pinky_up = cls.finger_up(hand_lms, 20, 18)

        index_bent = cls.finger_bent(hand_lms, 8, 6)
        middle_bent = cls.finger_bent(hand_lms, 12, 10)
        ring_bent = cls.finger_bent(hand_lms, 16, 14)
        pinky_bent = cls.finger_bent(hand_lms, 20, 18)

        pinch_ratio = cls.get_pinch_ratio(hand_lms)

        # 张开手掌：四指伸直且拇指远离食指
        if index_up and middle_up and ring_up and pinky_up and pinch_ratio > Params.OPEN_PALM_RATIO:
            return "open_palm"

        # 握拳：四指全部弯曲
        if index_bent and middle_bent and ring_bent and pinky_bent and pinch_ratio > Params.FIST_RATIO:
            return "fist"

        # 捏合：带迟滞，当前已是捏合时放宽退出条件
        if current_active == "pinch":
            if pinch_ratio < Params.PINCH_EXIT:
                return "pinch"
        else:
            if pinch_ratio < Params.PINCH_ENTER:
                return "pinch"

        # V SIGN：食指 + 中指伸直
        if index_up and middle_up and ring_bent and pinky_bent and pinch_ratio > Params.V_SIGN_RATIO:
            return "v_sign"

        # 指向：仅食指伸直，其余弯曲，且捏合距离足够大
        if pinch_ratio > Params.POINT_MIN_RATIO and index_up and middle_bent and ring_bent and pinky_bent:
            return "point"

        return None