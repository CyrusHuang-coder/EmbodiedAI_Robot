# 每次运行代码前必读：
# 1. 激活 conda 环境
# conda activate embodied_ai
# 2. 进入项目根目录（确保模型文件路径正确）
# cd /Users/huangtianzhi/Desktop/EmbodiedAI_Robot
# 3. 运行脚本
# python scripts/mediapipe_hands.py

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python.vision import hand_landmarker
from mediapipe.tasks.python.vision import HandLandmarkerOptions, RunningMode
import os
import sys
import requests
import time
import math
import signal
import atexit

# ---------- 手部骨骼连接定义 ----------
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),        # 拇指
    (0,5),(5,6),(6,7),(7,8),        # 食指
    (0,9),(9,10),(10,11),(11,12),   # 中指
    (0,13),(13,14),(14,15),(15,16), # 无名指
    (0,17),(17,18),(18,19),(19,20), # 小指
    (5,9),(9,13),(13,17)            # 掌骨连接
]

# ---------- 加载手部关键点模型 ----------
script_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(script_dir, "..", "hand_landmarker.task")
if not os.path.exists(MODEL_PATH):
    print(f"模型文件不存在：{MODEL_PATH}")
    sys.exit(1)

base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = HandLandmarkerOptions(
    base_options=base_options,
    running_mode=RunningMode.IMAGE,
    num_hands=1
)
landmarker = hand_landmarker.HandLandmarker.create_from_options(options)

# ---------- ESP32 通信 ----------
ESP32_IP = "192.168.4.1"
try:
    requests.get(f"http://{ESP32_IP}/mode?mode=gesture", timeout=0.2)
except:
    pass

last_send_time = {1: 0, 2: 0, 3: 0, 4: 0}
MIN_SEND_INTERVAL = 0.05   # 50 毫秒最小间隔
def send_servo(servo_id, angle):
    #发送舵机角度0~180,带频率限制
    global last_send_time
    # 频率限制：同一舵机在 MIN_SEND_INTERVAL 秒内不重复发送
    now = time.time()
    if now - last_send_time.get(servo_id, 0) < MIN_SEND_INTERVAL:
        return   # 忽略过于频繁的请求
    # 量化为 QUANTIZE_STEP 的倍数（如果已经定义了 QUANTIZE_STEP）
    angle = round(angle / QUANTIZE_STEP) * QUANTIZE_STEP
    angle = max(0, min(180, int(angle)))
    try:
        url = f"http://{ESP32_IP}/setGesture?servo={servo_id}&angle={angle}"
        requests.get(url, timeout=0.05)
        last_send_time[servo_id] = now
    except:
        pass
    time.sleep(0.002)

# ---------- 摄像头初始化 ----------
cap = cv2.VideoCapture(0)
WINDOW_NAME = "Embodied AI Gesture Control"
running = True
prev_time = time.time()
fps = 0

# ---------- 可调参数（UI） ----------
CENTER_DEAD_ZONE = 70           # 屏幕中心死区显示半径（像素），仅视觉提示

# ---------- 可调参数（Point 控制） ----------
DOMINANT_THRESHOLD = 1.35       # 主方向判定倍率，值越大越容易锁轴
AXIS_LOCK_FRAMES = 4            # 锁轴后保持的帧数，越大越稳定但反应慢
MOVE_DEAD_ZONE = 0.01          # 忽略小于此值的移动（归一化坐标）

# ---------- 可调参数（平滑） ----------
SMOOTH_ALPHA = 0.25             # 指数移动平均系数，越小越平滑但延迟大

# ---------- 可调参数（舵机更新阈值） ----------
SERVO_UPDATE_THRESHOLD = 1      # 角度变化小于此值不发送指令，减少抖动

# ---------- 可调参数（Pinch 捏合） ----------
PINCH_ENTER = 0.32              # 进入捏合模式的 pinch_ratio 上限（越小越难进入）
PINCH_EXIT = 0.42               # 退出捏合模式的 pinch_ratio 下限（越大越难退出）
POINT_MIN_RATIO = 0.50          # 进入 Point 模式的最小 pinch_ratio，防止误判

QUANTIZE_STEP = 5                    # 角度取整步长
SERVO_UPDATE_THRESHOLD = 4           # 改为 4°，减少指令数
# ---------- 机械安全限位 ----------
A_MIN = 20
A_MAX = 160
B_MIN = 0
B_MAX = 110
G_MIN = 0
G_MAX = 90

# ---------- 全局状态变量 ----------
robot_state = {
    "A": 90,
    "B": 0,
    "G": 0
}
last_base = -1
last_shoulder = -1
last_grip = -1

smooth_base = 90
smooth_shoulder = 0
smooth_grip = 0

current_base_angle = 90         # 用于速度累加控制的当前角度
current_shoulder_angle = 0

gesture_buffer = None           # 手势稳定缓冲区
gesture_count = 0

active_gesture = None           # 当前激活的连续手势（point / pinch）
interrupt_count = 0             # 手势中断计数，用于迟滞退出

last_open_palm_time = 0         # 归零冷却
last_fist_time = 0              # 抓取冷却

ab_locked = False               # A/B 轴锁定状态（比✌️切换）
current_mode = "TELEOP"
last_lock_time = 0
lock_message = ""
lock_message_time = 0
action_message = ""
action_message_time = 0

control_axis = None             # point 模式下的当前控制轴（A/B）
axis_lock_counter = 0           # 轴锁定剩余帧数

prev_point_x = None             # 前一帧食指位置，用于计算移动增量
prev_point_y = None

# ---------- 退出清理 ----------
def cleanup():
    global running
    running = False
    try:
        requests.get(f"http://{ESP32_IP}/mode?mode=web", timeout=0.2)
    except:
        pass
    try:
        cap.release()
    except:
        pass
    try:
        cv2.destroyAllWindows()
    except:
        pass
    try:
        landmarker.close()
    except:
        pass

def handle_exit(sig, frame):
    global running
    running = False

# ---------- 网页角度信息同步 ----------
def sync_angles():
    try:
        resp = requests.get(f"http://{ESP32_IP}/status", timeout=0.2)
        if resp.status_code == 200:
            data = resp.json()
            global current_base_angle, current_shoulder_angle, smooth_grip
            current_base_angle = data["A"]
            current_shoulder_angle = data["B"]
            smooth_grip = data["G"]
            robot_state["A"] = data["A"]
            robot_state["B"] = data["B"]
            robot_state["G"] = data["G"]
    except:
        pass

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)
atexit.register(cleanup)
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

# ---------- 数学工具 ----------
def clamp(v, vmin, vmax):
    return max(vmin, min(vmax, v))

def lerp(a, b, alpha):
    return a * (1 - alpha) + b * alpha

# ---------- 手指姿态判断 ----------
def finger_up(hand_lms, tip_idx, pip_idx):
    """指尖是否明显高于 PIP 关节（伸直）"""
    return hand_lms[tip_idx].y < hand_lms[pip_idx].y - 0.04

def finger_bent(hand_lms, tip_idx, pip_idx):
    """指尖是否明显低于 PIP 关节（弯曲）"""
    return hand_lms[tip_idx].y > hand_lms[pip_idx].y + 0.04

def get_palm_size(hand_lms):
    """估算手掌尺寸（手腕到中指 MCP）用于归一化"""
    wrist = hand_lms[0]
    middle_mcp = hand_lms[9]
    return math.hypot(wrist.x - middle_mcp.x, wrist.y - middle_mcp.y) + 1e-6

def get_pinch_ratio(hand_lms):
    """拇食指距离相对于手掌尺寸的比值"""
    thumb_tip = hand_lms[4]
    index_tip = hand_lms[8]
    dist = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
    return dist / get_palm_size(hand_lms)

# ---------- 手势分类（带迟滞） ----------
def classify_gesture(hand_lms, current_active):
    """
    返回手势字符串：thumbs_up / open_palm / fist / point / pinch / None
    current_active 用于 pinch 迟滞判断
    """
    index_up = finger_up(hand_lms, 8, 6)
    middle_up = finger_up(hand_lms, 12, 10)
    ring_up = finger_up(hand_lms, 16, 14)
    pinky_up = finger_up(hand_lms, 20, 18)

    index_bent = finger_bent(hand_lms, 8, 6)
    middle_bent = finger_bent(hand_lms, 12, 10)
    ring_bent = finger_bent(hand_lms, 16, 14)
    pinky_bent = finger_bent(hand_lms, 20, 18)

    pinch_ratio = get_pinch_ratio(hand_lms)

    # 张开手掌：四指伸直且拇指远离食指
    if index_up and middle_up and ring_up and pinky_up and pinch_ratio > 0.5:
        return "open_palm"

    # 握拳：四指全部弯曲
    if index_bent and middle_bent and ring_bent and pinky_bent and pinch_ratio > 0.38:
        return "fist"

    # 捏合：带迟滞，当前已是捏合时放宽退出条件
    if current_active == "pinch":
        if pinch_ratio < PINCH_EXIT:
            return "pinch"
    else:
        if pinch_ratio < PINCH_ENTER:
            return "pinch"
    # V SIGN：食指 + 中指伸直
    if (index_up and middle_up and ring_bent and pinky_bent and pinch_ratio > 0.45):
        return "v_sign"
    
    # 指向：仅食指伸直，其余弯曲，且捏合距离足够大
    if pinch_ratio > POINT_MIN_RATIO and index_up and middle_bent and ring_bent and pinky_bent:
        return "point"

    return None

# ---------- 绘制 UI 参考线 ----------
def draw_ui(frame):
    h, w, _ = frame.shape
    cx, cy = w // 2, h // 2
    line_color = (180,180,180)
    cv2.line(frame, (cx,0), (cx,h), line_color, 1)
    cv2.line(frame, (0,cy), (w,cy), line_color, 1)
    dz = CENTER_DEAD_ZONE
    cv2.rectangle(frame, (cx-dz, cy-dz), (cx+dz, cy+dz), (160,160,160), 1)

sync_angles() 

# ---------- 主循环 ----------
try:
    while running and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        current_time = time.time() 
        dt = current_time - prev_time
        prev_time = current_time
        if dt > 0:
            fps = 1.0 / dt
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        draw_ui(frame)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect(mp_image)

        if result.hand_landmarks:
            hand_lms = result.hand_landmarks[0]

            # 绘制骨架和关键点
            for (i, j) in HAND_CONNECTIONS:
                x1, y1 = int(hand_lms[i].x * w), int(hand_lms[i].y * h)
                x2, y2 = int(hand_lms[j].x * w), int(hand_lms[j].y * h)
                cv2.line(frame, (x1,y1), (x2,y2), (0,255,0), 2)
            for lm in hand_lms:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx,cy), 5, (0,0,255), -1)

            det_gesture = classify_gesture(hand_lms, active_gesture)

            # 左上角调试显示
            cv2.putText(frame, f"Det: {det_gesture}", (20,40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

            # ---------- 手势稳定计数 ----------
            if det_gesture == gesture_buffer:
                gesture_count += 1
            else:
                gesture_buffer = det_gesture
                gesture_count = 1

            # ---------- 一次性手势触发 ----------
            if gesture_count >= 5:
                # ✌️：切换 AB 锁定
                if det_gesture == "v_sign" and current_time - last_lock_time > 1.0:
                    ab_locked = not ab_locked
                    last_lock_time = current_time
                    if ab_locked:
                        lock_message = "AB LOCKED"
                    else:
                        lock_message = "AB UNLOCKED"
                    lock_message_time = current_time

                # 张开手掌：归零
                if det_gesture == "open_palm" and current_time - last_open_palm_time > 1.0:
                    action_message = "ZERO"
                    action_message_time = current_time                   
                    send_servo(1, 90)
                    send_servo(2, 0)
                    #send_servo(3, 180)   #最好先注释掉，就怕自由度超出
                    send_servo(4, 0)
                    #告诉内部程序角度已经更新
                    current_base_angle = 90
                    current_shoulder_angle = 0
                    smooth_base = 90
                    smooth_shoulder = 0
                    smooth_grip = 0
                    robot_state["A"] = 90
                    robot_state["B"] = 0
                    robot_state["G"] = 0
                    last_open_palm_time = current_time
                    active_gesture = None

                # 握拳：夹爪闭合
                elif det_gesture == "fist" and current_time - last_fist_time > 1.0:
                    action_message = "GRAB"
                    action_message_time = current_time
                    send_servo(4, 180)
                    robot_state["G"] = 180
                    smooth_grip = 180
                    last_grip = 180
                    last_fist_time = current_time
                    active_gesture = None
                    
            # ---------- 连续手势状态机（迟滞切换） ----------
            if det_gesture != active_gesture:
                interrupt_count += 1
                threshold = 10 if active_gesture == "pinch" else 6   # pinch 更难退出
                if interrupt_count >= threshold:
                    if det_gesture in ("point", "pinch"):
                        active_gesture = det_gesture
                    else:
                        active_gesture = None
                    interrupt_count = 0
                    control_axis = None
                    axis_lock_counter = 0
                    prev_point_x = None
                    prev_point_y = None
            else:
                interrupt_count = 0

            # ---------- Point 模式：速度累加控制 A/B 轴 ----------
            if active_gesture == "point" and not ab_locked:
                index_tip = hand_lms[8]
                px, py = index_tip.x, index_tip.y
                if prev_point_x is None:
                    prev_point_x, prev_point_y = px, py
                dx = px - prev_point_x
                dy = py - prev_point_y
                prev_point_x, prev_point_y = px, py
                if abs(dx) < MOVE_DEAD_ZONE: dx = 0
                if abs(dy) < MOVE_DEAD_ZONE: dy = 0
                abs_dx, abs_dy = abs(dx), abs(dy)

                # 主方向判定与锁轴
                if axis_lock_counter <= 0:
                    if abs_dx > abs_dy * DOMINANT_THRESHOLD and abs_dx > MOVE_DEAD_ZONE:
                        control_axis = "A"
                        axis_lock_counter = AXIS_LOCK_FRAMES
                    elif abs_dy > abs_dx * DOMINANT_THRESHOLD and abs_dy > MOVE_DEAD_ZONE:
                        control_axis = "B"
                        axis_lock_counter = AXIS_LOCK_FRAMES
                    else:
                        control_axis = None
                else:
                    axis_lock_counter -= 1

                # A 轴（底座）：手指水平偏移转换成速度累加
                if control_axis == "A":
                    if control_axis == "A":
                        EDGE_THRESH = 0.12   # 边缘锁死区宽度（可调参数）
                        if px > 1.0 - EDGE_THRESH:          # 手指在右边缘
                            speed = 28 * 0.5                 # 恒定正向最大速度（系数28可调）
                        elif px < EDGE_THRESH:               # 手指在左边缘
                            speed = -28 * 0.5                # 恒定负向最大速度
                        else:
                            offset_x = px - 0.5
                            if abs(offset_x) < 0.05:
                                offset_x = 0
                            speed = offset_x * 28
                    current_base_angle += speed
                    current_base_angle = clamp(current_base_angle, A_MIN, A_MAX)
                    smooth_base = lerp(smooth_base, current_base_angle, 0.2)
                    smooth_base_int = int(smooth_base)
                    if abs(smooth_base_int - last_base) > SERVO_UPDATE_THRESHOLD:
                        send_servo(1, smooth_base_int)
                        last_base = smooth_base_int
                        robot_state["A"] = smooth_base_int
                    cv2.putText(frame, "VELOCITY X", (40,80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,255), 2)

                # B 轴（肩）：手指垂直偏移转换成速度累加
                elif control_axis == "B":
                    # 用手指运动增量控制速度（更跟手）
                    speed = -dy * 220
                    # 小运动过滤
                    if abs(speed) < 1:
                        speed = 0
                    if current_shoulder_angle >= B_MAX and speed > 0:
                        speed = 0
                    if current_shoulder_angle <= B_MIN and speed < 0:
                        speed = 0
                    current_shoulder_angle += speed
                    current_shoulder_angle = clamp(current_shoulder_angle, B_MIN, B_MAX)
                    smooth_shoulder = lerp(smooth_shoulder, current_shoulder_angle, 0.2)
                    smooth_shoulder_int = int(smooth_shoulder)
                    if abs(smooth_shoulder_int - last_shoulder) > SERVO_UPDATE_THRESHOLD:
                        send_servo(2, smooth_shoulder_int)
                        last_shoulder = smooth_shoulder_int
                        robot_state["B"] = smooth_shoulder_int
                    cv2.putText(frame, "VELOCITY Y", (40,80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,200,0), 2)
                else:
                    cv2.putText(frame, "POINT -> WAIT DIRECTION", (40,80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200,200,200), 2)

            # ---------- Pinch 模式：捏合控制夹爪 ----------
            elif active_gesture == "pinch":
                pinch_ratio = get_pinch_ratio(hand_lms)
                grip_angle = int((pinch_ratio - 0.12) * 260)   # 【可调参数】映射系数 260，偏移 -0.12
                grip_angle = clamp(grip_angle, G_MIN, G_MAX)
                smooth_grip = lerp(smooth_grip, grip_angle, 0.20)
                smooth_grip_int = int(smooth_grip)
                if abs(smooth_grip_int - last_grip) > 2:
                    send_servo(4, smooth_grip_int)
                    last_grip = smooth_grip_int
                    robot_state["G"] = smooth_grip_int
                cv2.putText(frame, f"PINCH  G:{smooth_grip_int}", (40,80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,0), 2)
                # 可视化捏合线
                thumb_tip = hand_lms[4]
                index_tip = hand_lms[8]
                tx, ty = int(thumb_tip.x * w), int(thumb_tip.y * h)
                ix, iy = int(index_tip.x * w), int(index_tip.y * h)
                cv2.line(frame, (tx,ty), (ix,iy), (255,255,0), 3)

        else:
            # 没检测到手时重置状态
            active_gesture = None
            control_axis = None
            axis_lock_counter = 0
            prev_point_x = None
            prev_point_y = None

        # ---------- ROBOT HUD ----------
        cv2.putText(
            frame,
            f"FPS: {int(fps)}",
            (w - 180, 160),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0,255,0),
            2
        )
        cv2.putText(
            frame,
            f"MODE: {current_mode}",
            (w - 220, 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255,255,255),
            2
        )
        cv2.putText(
            frame,
            f"A: {robot_state['A']:3d}",
            (w - 180, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0,255,255),
            2
        )
        cv2.putText(
            frame,
            f"B: {robot_state['B']:3d}",
            (w - 180, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255,200,0),
            2
        )
        cv2.putText(
            frame,
            f"G: {robot_state['G']:3d}",
            (w - 180, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255,255,0),
            2
        )
        # ---------- 状态条 ----------
        bar_x = w - 180
        bar_w = 120
        bar_h = 14
        # A轴
        cv2.rectangle(frame, (bar_x,240), (bar_x + bar_w,240 + bar_h), (80,80,80), -1)
        cv2.rectangle(
            frame,
            (bar_x,240),
            (bar_x + int(robot_state["A"]/180 * bar_w),240 + bar_h),
            (0,255,255),
            -1
        )
        # B轴
        cv2.rectangle(frame, (bar_x,270), (bar_x + bar_w,270 + bar_h), (80,80,80), -1)
        cv2.rectangle(
            frame,
            (bar_x,270),
            (bar_x + int(robot_state["B"]/180 * bar_w),270 + bar_h),
            (255,200,0),
            -1
        )
        # G轴
        cv2.rectangle(frame, (bar_x,300), (bar_x + bar_w,300 + bar_h), (80,80,80), -1)
        cv2.rectangle(
            frame,
            (bar_x,300),
            (bar_x + int(robot_state["G"]/180 * bar_w),300 + bar_h),
            (255,255,0),
            -1
        )

        cv2.putText(frame, "A", (bar_x - 25,252),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        cv2.putText(frame, "B", (bar_x - 25,282),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,200,0), 2)
        cv2.putText(frame, "G", (bar_x - 25,312),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        
        # ---------- LIMIT WARNING ----------
        if robot_state["B"] >= B_MAX - 5:
            cv2.putText(
                frame,
                "B LIMIT",
                (w - 220, 340),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0,0,255),
                2
            )
        
        # ---------- 底部状态与提示显示 ----------
        cv2.putText(frame, f"ACTIVE: {active_gesture}", (20, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        # AB锁定状态
        if ab_locked:
            cv2.putText(frame, "AB LOCKED", (20,140), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 3)
        # LOCK / UNLOCK 提示
        if current_time - lock_message_time < 1.5:
            if "UNLOCKED" in lock_message:
                color = (0,255,0)
            else:
                color = (0,0,255)
            cv2.putText(frame, lock_message, (20,180), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 3)

        # GRAB / ZERO 提示
        if current_time - action_message_time < 1.5:
            color = (255,255,255)
            if action_message == "GRAB":
                color = (0,255,0)
            elif action_message == "ZERO":
                color = (255,0,0)
            cv2.putText(
                frame,
                action_message,
                (20,220),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                color,
                4
            )
        cv2.imshow(WINDOW_NAME, frame)

        # 退出检测
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

finally:
    cleanup()