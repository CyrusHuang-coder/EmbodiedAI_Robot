import cv2
import time
import signal
import atexit
import requests
import sys

from vision.hand_tracking import HandTracker
from logic.state_manager import StateManager
from logic.gesture_logic import GestureLogic
from control.esp32_controller import ServoController
from control.servo_mapper import ServoMapper
from control.motion_filter import MotionFilter
from config.params import Params
from ui.hud_renderer import HUDRenderer

# ================= 初始化 =================
params = Params()
state = StateManager()
servo = ServoController(Params.ESP32_IP, Params.QUANTIZE_STEP)
mapper = ServoMapper()
mfilter = MotionFilter(0.2)
tracker = HandTracker()
hud = HUDRenderer(state)

# 尝试启动时同步机械臂当前角度（需 ESP32 固件支持 /status 接口）
try:
    resp = requests.get(f"http://{Params.ESP32_IP}/status", timeout=0.2)
    if resp.status_code == 200:
        data = resp.json()
        state.robot_state["A"] = data["A"]
        state.robot_state["B"] = data["B"]
        state.robot_state["G"] = data["G"]
except:
    pass

# ================= 摄像头 =================
cap = cv2.VideoCapture(0)
WINDOW_NAME = "Embodied AI Gesture Control"
running = True
prev_time = time.time()

# ================= 退出清理 =================
def cleanup():
    global running
    running = False
    try:
        requests.get(f"http://{Params.ESP32_IP}/mode?mode=web", timeout=0.2)
    except:
        pass
    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()
    tracker.close()

def handle_exit(sig, frame):
    global running
    running = False

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)
atexit.register(cleanup)

# ================= 主循环 =================
try:
    while running and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # 时间计算
        current_time = time.time()
        dt = current_time - prev_time
        prev_time = current_time
        if dt > 0:
            state.fps = 1.0 / dt

        # 镜像翻转
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2] 
        
        # 手部追踪（绘制骨架和关键点）
        frame, lms = tracker.process(frame)

        # 手势处理
        if lms:
            g = GestureLogic.classify_gesture(lms, state.active_gesture)
            state.gesture_buffer = g

            # 左上角调试显示
            cv2.putText(frame, f"Det: {g}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

            # V 手势：切换 AB 锁定（带冷却）
            if g == "v_sign" and current_time - state.last_lock_time > 1.0:
                state.toggle_lock()
                state.last_lock_time = current_time
                if state.ab_locked:
                    state.lock_message = "AB LOCKED"
                else:
                    state.lock_message = "AB UNLOCKED"
                state.lock_message_time = current_time

            # 张开手掌：归零（冷却）
            if g == "open_palm" and current_time - state.last_open_palm_time > 1.0:
                servo.send(1, 90)
                servo.send(2, 0)
                servo.send(4, 0)
                state.robot_state["A"] = 90
                state.robot_state["B"] = 0
                state.robot_state["G"] = 0
                # 重置内部角度变量（现在属于 state）
                state.current_base_angle = 90
                state.current_shoulder_angle = 0
                state.smooth_base = 90
                state.smooth_shoulder = 0
                state.smooth_grip = 0
                state.active_gesture = None
                state.action_message = "ZERO"
                state.action_message_time = current_time
                state.last_open_palm_time = current_time
                cv2.putText(frame, "ZERO", (40, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 3)

            # 握拳：抓取（冷却）
            elif g == "fist" and current_time - state.last_fist_time > 1.0:
                servo.send(4, 180)
                state.robot_state["G"] = 180
                state.smooth_grip = 180
                state.last_grip = 180
                state.active_gesture = None
                state.action_message = "GRAB"
                state.action_message_time = current_time
                state.last_fist_time = current_time
                cv2.putText(frame, "GRAB", (40, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 3)

            # ===== 连续手势状态机（带迟滞） =====
            if g != state.active_gesture:
                state.interrupt_count += 1
                threshold = 10 if state.active_gesture == "pinch" else 6
                if state.interrupt_count >= threshold:
                    if g in ("point", "pinch"):
                        state.active_gesture = g
                    else:
                        state.active_gesture = None
                    state.interrupt_count = 0
                    # 重置 point 控制状态
                    state.control_axis = None
                    state.axis_lock_counter = 0
                    state.prev_point_x = None
                    state.prev_point_y = None
            else:
                state.interrupt_count = 0

            # ===== Point 模式：速度累加控制 A/B 轴 =====
            if state.active_gesture == "point" and not state.ab_locked:
                index_tip = lms[8]
                px, py = index_tip.x, index_tip.y
                if state.prev_point_x is None:
                    state.prev_point_x, state.prev_point_y = px, py

                dx = px - state.prev_point_x
                dy = py - state.prev_point_y
                state.prev_point_x, state.prev_point_y = px, py

                # 死区过滤
                if abs(dx) < Params.MOVE_DEAD_ZONE: dx = 0
                if abs(dy) < Params.MOVE_DEAD_ZONE: dy = 0
                abs_dx, abs_dy = abs(dx), abs(dy)

                # 主方向判定与锁轴
                if state.axis_lock_counter <= 0:
                    if abs_dx > abs_dy * Params.DOMINANT_THRESHOLD and abs_dx > Params.MOVE_DEAD_ZONE:
                        state.control_axis = "A"
                        state.axis_lock_counter = Params.AXIS_LOCK_FRAMES
                    elif abs_dy > abs_dx * Params.DOMINANT_THRESHOLD and abs_dy > Params.MOVE_DEAD_ZONE:
                        state.control_axis = "B"
                        state.axis_lock_counter = Params.AXIS_LOCK_FRAMES
                    else:
                        state.control_axis = None
                else:
                    state.axis_lock_counter -= 1

                # A 轴控制（边缘锁死 + 速度映射）
                if state.control_axis == "A":
                    EDGE_THRESH = Params.EDGE_THRESH
                    if px > 1.0 - EDGE_THRESH:
                        speed = Params.SPEED_A * Params.SPEED_A_EDGE_FACTOR
                    elif px < EDGE_THRESH:
                        speed = -Params.SPEED_A * Params.SPEED_A_EDGE_FACTOR
                    else:
                        offset_x = px - 0.5
                        if abs(offset_x) < 0.05: offset_x = 0
                        speed = offset_x * Params.SPEED_A

                    state.current_base_angle += speed
                    state.current_base_angle = max(Params.A_MIN, min(Params.A_MAX, state.current_base_angle))
                    state.smooth_base += (state.current_base_angle - state.smooth_base) * Params.SMOOTH_ALPHA
                    smooth_int = int(state.smooth_base)

                    if abs(smooth_int - state.last_base) > Params.SERVO_UPDATE_THRESHOLD:
                        servo.send(1, smooth_int)
                        state.last_base = smooth_int
                        state.robot_state["A"] = smooth_int

                    cv2.putText(frame, "VELOCITY X", (40, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,255), 2)

                # B 轴控制（dy 增量速度）
                elif state.control_axis == "B":
                    speed = -dy * Params.SPEED_B
                    if abs(speed) < 1: speed = 0
                    if state.current_shoulder_angle >= Params.B_MAX and speed > 0:
                        speed = 0
                    if state.current_shoulder_angle <= Params.B_MIN and speed < 0:
                        speed = 0

                    state.current_shoulder_angle += speed
                    state.current_shoulder_angle = max(Params.B_MIN, min(Params.B_MAX, state.current_shoulder_angle))
                    state.smooth_shoulder += (state.current_shoulder_angle - state.smooth_shoulder) * Params.SMOOTH_ALPHA
                    smooth_int = int(state.smooth_shoulder)

                    if abs(smooth_int - state.last_shoulder) > Params.SERVO_UPDATE_THRESHOLD:
                        servo.send(2, smooth_int)
                        state.last_shoulder = smooth_int
                        state.robot_state["B"] = smooth_int

                    cv2.putText(frame, "VELOCITY Y", (40, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,200,0), 2)
                else:
                    cv2.putText(frame, "POINT -> WAIT DIRECTION", (40, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200,200,200), 2)

            # ===== Pinch 模式：捏合控制夹爪 =====
            elif state.active_gesture == "pinch":
                pinch_ratio = GestureLogic.get_pinch_ratio(lms)
                grip_angle = int((pinch_ratio - Params.PINCH_MAPPING_OFFSET) * Params.PINCH_MAPPING_COEFF)
                grip_angle = max(Params.G_MIN, min(Params.G_MAX, grip_angle))
                state.smooth_grip += (grip_angle - state.smooth_grip) * 0.2
                smooth_int = int(state.smooth_grip)

                if abs(smooth_int - state.last_grip) > 2:
                    servo.send(4, smooth_int)
                    state.last_grip = smooth_int
                    state.robot_state["G"] = smooth_int

                cv2.putText(frame, f"PINCH  G:{smooth_int}", (40, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,0), 2)
                # 捏合可视化连接线
                thumb_tip = lms[4]
                index_tip = lms[8]
                tx, ty = int(thumb_tip.x * w), int(thumb_tip.y * h)
                ix, iy = int(index_tip.x * w), int(index_tip.y * h)
                cv2.line(frame, (tx, ty), (ix, iy), (255,255,0), 3)

        # 绘制 UI 辅助线与 HUD
        hud.draw_ui_guides(frame)
        hud.draw_hud(frame, current_time)

        cv2.imshow(WINDOW_NAME, frame)

        # 退出检测
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

finally:
    cleanup()