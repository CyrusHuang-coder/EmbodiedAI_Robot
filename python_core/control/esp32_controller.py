import time
import requests

class ServoController:
    """舵机控制器，通过 HTTP 请求向 ESP32 发送角度指令，并内置发送频率限制。"""
    def __init__(self, ip="192.168.4.1", min_interval=0.05):
        """
        初始化控制器。
        :param ip: ESP32 的 IP 地址，默认为手势控制热点地址。
        :param min_interval: 同一舵机两次发送的最小间隔（秒），用于限流。
        """
        self.ip = ip
        self.min_interval = min_interval
        self.last_send_time = {1: 0, 2: 0, 3: 0, 4: 0}  # 记录每个舵机的上次发送时间

    def send(self, servo_id, angle):
        """
        向指定舵机发送角度指令（0~180）。
        若距离上次发送不足 min_interval 秒，则直接返回，不重复发送。
        :param servo_id: 舵机编号 (1-4)
        :param angle: 目标角度，会被限制在 0~180 范围内
        """
        now = time.time()

        # 频率限制：同一舵机在 min_interval 内不重复发送
        if now - self.last_send_time.get(servo_id, 0) < self.min_interval:
            return

        # 角度限幅并取整
        angle = max(0, min(180, int(angle)))

        try:
            url = f"http://{self.ip}/setGesture?servo={servo_id}&angle={angle}"
            requests.get(url, timeout=0.05)          # 非阻塞快速请求
            self.last_send_time[servo_id] = now       # 更新发送时间
        except:
            pass  # 忽略网络错误，避免中断主程序

        time.sleep(0.002)  # 极短延迟，给 ESP32 留出处理时间