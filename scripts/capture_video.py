# scripts/capture_video.py 示例内容
import cv2
import time

cap = cv2.VideoCapture(0)  # 打开默认摄像头
if not cap.isOpened():
    print("无法打开摄像头,请检查权限或端口")
    exit()

print("摄像头打开成功, 按'q'键退出, 或等待60秒后自动退出")
start_time = time.time()    #获取此时实时时间

while True:
    ret, frame = cap.read()
    # cap.read() 从摄像头中抓取一帧图像。返回两个值：
    # ret(布尔值): 是否成功读取到帧。成功为 True, 失败为 False(例如摄像头断开)。
    # frame: 实际图像数据,以 NumPy 数组形式存储(三维数组，形状为 [高度, 宽度, 3]，颜色通道顺序为 BGR)
    
    if not ret:
        print("无法读取视频帧")
        break

    cv2.imshow("Camera Stream", frame)

    #cv2.waitKey(1) 等待键盘输入 1 毫秒。返回值是按键的 ASCII 码（如果没有按键，则返回 -1）
    #& 0xFF 是为了确保只取低 8 位（兼容 64 位系统的返回值）
    #ord('q') 返回字符 'q' 的 ASCII 码
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        print("手动退出退出视频流")
        break
    if time.time() - start_time > 60:
        print("时间超过60秒后自动退出")
        break

cap.release()
cv2.destroyAllWindows()