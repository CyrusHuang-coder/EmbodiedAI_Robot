import cv2
class HUDRenderer:
    """
    负责在视频帧上绘制所有辅助 UI：中心线、死区、角度文字、状态条、提示信息等。
    所需数据从 StateManager 实例中读取。
    """

    def __init__(self, state):
        """
        :param state: StateManager 实例，包含所有需要显示的运行时信息
        """
        self.state = state

        # 布局常量（可根据需要调整）
        self.CENTER_DEAD_ZONE = 70          # 中心死区框半径
        self.HUD_RIGHT_MARGIN = 180         # 右侧 HUD 区域离右边缘距离
        self.BAR_WIDTH = 120                # 状态条宽度
        self.BAR_HEIGHT = 14                # 状态条高度

    def draw_ui_guides(self, frame):
        """绘制中心十字线和死区框（仅视觉辅助）"""
        h, w, _ = frame.shape
        cx, cy = w // 2, h // 2
        line_color = (180, 180, 180)

        cv2.line(frame, (cx, 0), (cx, h), line_color, 1)
        cv2.line(frame, (0, cy), (w, cy), line_color, 1)

        dz = self.CENTER_DEAD_ZONE
        cv2.rectangle(
            frame,
            (cx - dz, cy - dz),
            (cx + dz, cy + dz),
            (160, 160, 160),
            1
        )

    def draw_hud(self, frame, current_time):
        """
        绘制完整的 HUD：角度数据、状态条、锁定/动作提示、警告等。
        :param frame: 要绘制的图像帧
        :param current_time: 当前时间戳（秒），用于提示的闪烁显示
        """
        h, w, _ = frame.shape
        right_x = w - self.HUD_RIGHT_MARGIN

        # ---- 角度数值 ----
        cv2.putText(frame, f"A: {self.state.robot_state['A']:3d}", (right_x, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)
        cv2.putText(frame, f"B: {self.state.robot_state['B']:3d}", (right_x, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,200,0), 2)
        cv2.putText(frame, f"G: {self.state.robot_state['G']:3d}", (right_x, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,0), 2)

        # ---- FPS & MODE ----
        cv2.putText(frame, f"FPS: {int(self.state.fps)}", (right_x, 160),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(frame, f"MODE: {self.state.mode}", (w - 220, 200),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)

        # ---- 状态条 ----
        bar_x = right_x
        bar_w = self.BAR_WIDTH
        bar_h = self.BAR_HEIGHT

        for axis, color in [("A", (0,255,255)), ("B", (255,200,0)), ("G", (255,255,0))]:
            y_top = 240 + (axis == "B") * 30 + (axis == "G") * 60   # 240 / 270 / 300
            # 背景
            cv2.rectangle(frame, (bar_x, y_top), (bar_x + bar_w, y_top + bar_h), (80,80,80), -1)
            # 填充
            fill_ratio = self.state.robot_state[axis] / 180.0
            cv2.rectangle(frame, (bar_x, y_top),
                          (bar_x + int(fill_ratio * bar_w), y_top + bar_h), color, -1)
            # 轴标签
            cv2.putText(frame, axis, (bar_x - 25, y_top + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # ---- 警告 ----
        if self.state.robot_state["B"] >= self.state.B_MAX - 5:
            cv2.putText(frame, "B LIMIT", (w - 220, 340),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

        # ---- 底部活动手势 ----
        cv2.putText(frame, f"ACTIVE: {self.state.active_gesture}", (20, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

        # ---- AB 锁定状态 ----
        if self.state.ab_locked:
            cv2.putText(frame, "AB LOCKED", (20, 140),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 3)

        # ---- 锁定/解锁消息 ----
        if current_time - self.state.lock_message_time < 1.5:
            color = (0,255,0) if "UNLOCKED" in self.state.lock_message else (0,0,255)
            cv2.putText(frame, self.state.lock_message, (20, 180),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, color, 3)

        # ---- GRAB / ZERO 提示 ----
        if current_time - self.state.action_message_time < 1.5:
            if self.state.action_message == "GRAB":
                color = (0,255,0)
            elif self.state.action_message == "ZERO":
                color = (255,0,0)
            else:
                color = (255,255,255)
            cv2.putText(frame, self.state.action_message, (20, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 4)