class Params:
    """
    全局可调参数和常量配置
    使用方式：from config.params import Params
    """
    # ---------- 网络与窗口 ----------
    ESP32_IP = "192.168.4.1"
    WINDOW_NAME = "Embodied AI Gesture Control"

    # ---------- UI ----------
    CENTER_DEAD_ZONE = 70               # 屏幕中心死区显示半径（像素）

    # ---------- Point 控制 ----------
    DOMINANT_THRESHOLD = 1.35           # 主方向判定倍率，值越大越容易锁轴
    AXIS_LOCK_FRAMES = 4                # 锁轴后保持的帧数
    MOVE_DEAD_ZONE = 0.01               # 忽略小于此值的移动（归一化坐标）

    # ---------- 平滑 ----------
    SMOOTH_ALPHA = 0.25                 # 指数移动平均系数

    # ---------- 舵机更新 ----------
    SERVO_UPDATE_THRESHOLD = 4           # 角度变化超过此值才发送指令
    QUANTIZE_STEP = 5                    # 发送角度的取整步长（5°一跳）
    MIN_SEND_INTERVAL = 0.05             # 同一舵机两次发送的最小间隔（秒）

    # ---------- Pinch 捏合 ----------
    PINCH_ENTER = 0.32                  # 进入捏合模式的 pinch_ratio 上限
    PINCH_EXIT = 0.42                   # 退出捏合模式的 pinch_ratio 下限
    POINT_MIN_RATIO = 0.50              # 进入 Point 模式的最小 pinch_ratio

    # ---------- 机械安全限位 ----------
    A_MIN = 20
    A_MAX = 160
    B_MIN = 0
    B_MAX = 110
    G_MIN = 0
    G_MAX = 90

    # ---------- 手势分类阈值 ----------
    OPEN_PALM_RATIO = 0.5               # 张开手掌要求 pinch_ratio > 该值
    FIST_RATIO = 0.38                   # 握拳要求 pinch_ratio > 该值
    V_SIGN_RATIO = 0.45                 # V 手势要求 pinch_ratio > 该值

    # ---------- 手指弯曲判断容差 ----------
    FINGER_UP_TOLERANCE = 0.04          # 指尖高于 PIP 关节的最小差值
    FINGER_BENT_TOLERANCE = 0.04        # 指尖低于 PIP 关节的最小差值

    # ---------- Point 速度控制 ----------
    EDGE_THRESH = 0.12                  # 边缘锁死区宽度（归一化坐标）
    SPEED_A = 28                        # A 轴速度系数
    SPEED_A_EDGE_FACTOR = 0.5           # 边缘恒定速度占 SPEED_A 的比例
    SPEED_B = 220                       # B 轴速度系数（用于 dy 增量）

    # ---------- Pinch 映射参数 ----------
    PINCH_MAPPING_OFFSET = 0.12         # 映射公式中的偏移量
    PINCH_MAPPING_COEFF = 260           # 映射公式中的乘数

    # ---------- 手势状态机 ----------
    GESTURE_CONFIRM_FRAMES = 5          # 一次性手势需要的连续帧数
    CONTINUOUS_SWITCH_THRESHOLD = 6     # 普通连续手势切换中断帧数
    PINCH_SWITCH_THRESHOLD = 10         # pinch 手势切换中断帧数（更难退出）

    # ---------- 归零角度 ----------
    ZERO_A = 90
    ZERO_B = 0
    ZERO_C = 180
    ZERO_G = 0

    # ---------- HUD 显示位置偏移 ----------
    HUD_RIGHT_MARGIN = 180              # HUD 从右侧边缘的偏移（像素）
    BAR_WIDTH = 120                     # 状态条宽度
    BAR_HEIGHT = 14                     # 状态条高度