class StateManager:
    def __init__(self):
        # ----- 手势状态 -----
        self.active_gesture = None          # 当前激活的连续手势 (point/pinch/None)
        self.gesture_buffer = None          # 上帧检测的手势，用于稳定计数
        self.gesture_count = 0              # 连续相同手势的帧数

        # ----- 锁定与模式 -----
        self.ab_locked = False
        self.mode = "TELEOP"

        # ----- 冷却时间戳 -----
        self.last_open_palm_time = 0
        self.last_fist_time = 0
        self.last_lock_time = 0

        # ----- 提示消息 -----
        self.lock_message = ""
        self.lock_message_time = 0
        self.action_message = ""
        self.action_message_time = 0

        # ----- 舵机实时角度 (供 HUD 显示) -----
        self.robot_state = {
            "A": 90,
            "B": 0,
            "G": 0
        }

        # ----- 其他 HUD 信息 -----
        self.fps = 0
        self.B_MAX = 110                  # B 轴安全上限，按实际修改
        
        # ----- Point 控制状态变量 -----
        self.prev_point_x = None
        self.prev_point_y = None
        self.control_axis = None
        self.axis_lock_counter = 0
        self.current_base_angle = 90          # 初始 A 轴角度（可从同步获取）
        self.current_shoulder_angle = 0
        # 平滑值（与手势控制共用）
        self.smooth_base = 90
        self.smooth_shoulder = 0
        self.smooth_grip = 0
        # 上一次发送的角度（用于死区）
        self.last_base = -1
        self.last_shoulder = -1
        self.last_grip = -1
        # 中断计数器（用于连续手势切换）
        self.interrupt_count = 0

    def update_gesture(self, g):
        self.active_gesture = g

    def toggle_lock(self):
        self.ab_locked = not self.ab_locked