import requests

ESP32_IP = "192.168.4.1"

requests.get(f"http://{ESP32_IP}/mode?mode=gesture")

requests.get(f"http://{ESP32_IP}/setGesture?servo=2&angle=90")