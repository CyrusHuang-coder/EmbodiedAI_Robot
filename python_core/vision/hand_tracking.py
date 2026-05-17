import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
import os, sys

HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12),
    (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17)
]

class HandTracker:
    def __init__(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, "..", "hand_landmarker.task")
        if not os.path.exists(model_path):
            print(f"模型文件不存在：{model_path}")
            sys.exit(1)
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = HandLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.IMAGE,
            num_hands=1
        )
        self.landmarker = HandLandmarker.create_from_options(options)

    def detect(self, mp_image):
        result = self.landmarker.detect(mp_image)
        if result.hand_landmarks:
            return result.hand_landmarks[0]
        return None

    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        lms = self.detect(mp_image)

        if lms:
            h, w, _ = frame.shape
            # 绘制骨架
            for (i, j) in HAND_CONNECTIONS:
                x1, y1 = int(lms[i].x * w), int(lms[i].y * h)
                x2, y2 = int(lms[j].x * w), int(lms[j].y * h)
                cv2.line(frame, (x1, y1), (x2, y2), (0,255,0), 2)
            # 绘制关键点
            for lm in lms:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 5, (0,0,255), -1)

        return frame, lms

    def close(self):
        self.landmarker.close()