#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>

// ========== 引脚定义 ==========
#define SERVO_A_PIN   13   // 基座 A 轴
#define SERVO_B_PIN   14   // 肩   B 轴
#define SERVO_C_PIN   27   // 肘   C 轴
#define SERVO_G_PIN   26   // 夹爪 G 轴

// ========== 机械零点（软件角度） ==========
const int ZERO_A = 90;
const int ZERO_B = 0;
const int ZERO_C = 180;
const int ZERO_G = 0;

// ========== 舵机对象 ==========
Servo servoA, servoB, servoC, servoG;

// 当前角度 与 目标角度 （索引 0:A,1:B,2:C,3:G）
int current[4] = {ZERO_A, ZERO_B, ZERO_C, ZERO_G};
int target[4]  = {ZERO_A, ZERO_B, ZERO_C, ZERO_G};

// 手势模式状态：网页控制时让手势控制失效
bool gestureMode = false;
unsigned long lastGestureCmdMs = 0;
const unsigned long GESTURE_TIMEOUT_MS = 800;   // 0.8s没有手势就回到网页控制

// 速度控制
int speedPercent = 70;
const int BASE_STEP_DELAY_MS = 5;   // 最快时每步延时5ms

int getStepDelay() {
    // 速度0% -> 200ms, 100% -> BASE_STEP_DELAY_MS
    int delayMs = map(speedPercent, 0, 100, BASE_STEP_DELAY_MS * 40, BASE_STEP_DELAY_MS);
    return constrain(delayMs, BASE_STEP_DELAY_MS, 200);
}

void updateEasing() {
    bool changed = false;
    for (int i = 0; i < 4; i++) {
        if (current[i] != target[i]) {
            int step = (target[i] > current[i]) ? 1 : -1;
            current[i] += step;
            current[i] = constrain(current[i], 0, 180);
            changed = true;
        }
    }
    if (changed) {
        servoA.write(current[0]);
        servoB.write(current[1]);
        servoC.write(current[2]);
        servoG.write(current[3]);
        delay(getStepDelay());
    }
}

// ========== WiFi 热点 ==========
const char* ssid = "DolphinArm";
const char* password = "12345678";
WebServer server(80);

// ========== 网页内容 ==========
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>海豚机械臂 - 机械零点版</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: system-ui, sans-serif; background: #f0f4f8; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { max-width: 550px; width: 100%; background: white; border-radius: 32px; padding: 24px 20px 32px; box-shadow: 0 8px 20px rgba(0,0,0,0.1); text-align: center; }
        h1 { font-size: 1.8rem; color: #1e2f5e; margin: 0 0 0.5rem; }
        .sub { color: #5a6e8a; margin-bottom: 1.5rem; font-size: 0.9rem; }
        .slider-group { margin: 20px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
        .slider-group label { font-weight: 600; width: 70px; text-align: left; color: #1f3a6b; }
        input[type="range"] { flex: 2; min-width: 180px; height: 6px; border-radius: 10px; background: #d0ddeb; -webkit-appearance: none; appearance: none; }
        input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 20px; height: 20px; background: #2c7da0; border-radius: 50%; cursor: pointer; border: 2px solid white; }
        .value { width: 52px; background: #eef2f7; border-radius: 30px; padding: 4px 0; font-weight: bold; color: #0059b3; }
        button { background: #2c7da0; border: none; color: white; font-size: 1rem; font-weight: 600; padding: 10px 24px; border-radius: 40px; margin: 12px 8px 0; cursor: pointer; transition: 0.2s; }
        button:hover { background: #1f5e7a; transform: scale(0.97); }
        .status { margin-top: 20px; font-size: 0.8rem; color: #2c7da0; background: #e9f0f5; padding: 8px; border-radius: 28px; word-break: break-word; }
        .btn-zero { background: #5a6e8a; }
        .btn-zero:hover { background: #3e526e; }
    </style>
</head>
<body>
<div class="container">
    <h1>🐬 海豚机械臂</h1>
    <div class="sub">机械零点已标定 | 纯手动控制</div>

    <div class="slider-group"><label>基座(A)</label><input type="range" id="jointA" min="0" max="180" value="90" step="1"><span class="value" id="valA">90</span></div>
    <div class="slider-group"><label>肩(B)</label><input type="range" id="jointB" min="0" max="180" value="0" step="1"><span class="value" id="valB">0</span></div>
    <div class="slider-group"><label>肘(C)</label><input type="range" id="jointC" min="0" max="180" value="180" step="1"><span class="value" id="valC">180</span></div>
    <div class="slider-group"><label>夹爪(G)</label><input type="range" id="jointG" min="0" max="180" value="0" step="1"><span class="value" id="valG">0</span></div>
    <div class="slider-group"><label>运动速度</label><input type="range" id="speed" min="0" max="100" value="70" step="1"><span class="value" id="speedVal">70</span></div>

    <div><button id="zeroBtn" class="btn-zero">🔄 归零 (机械零点)</button></div>

    <div class="status" id="statusMsg">⚡ 等待连接 ESP32...</div>
</div>

<script>
    const ESP32_IP = "192.168.4.1";
    const BASE_URL = `http://${ESP32_IP}`;

    // DOM 元素
    const sliders = {
        A: document.getElementById('jointA'),
        B: document.getElementById('jointB'),
        C: document.getElementById('jointC'),
        G: document.getElementById('jointG')
    };
    const spans = {
        A: document.getElementById('valA'),
        B: document.getElementById('valB'),
        C: document.getElementById('valC'),
        G: document.getElementById('valG')
    };
    const speedSlider = document.getElementById('speed');
    const speedSpan = document.getElementById('speedVal');
    const zeroBtn = document.getElementById('zeroBtn');
    const statusDiv = document.getElementById('statusMsg');

    // 轴名称到ID的映射 (ESP32端使用1:A,2:B,3:C,4:G)
    const nameToId = {A:1, B:2, C:3, G:4};

    // 发送角度指令
    async function sendAngle(axisName, angle) {
        const servoId = nameToId[axisName];
        try {
            const url = `${BASE_URL}/set?servo=${servoId}&angle=${angle}`;
            const resp = await fetch(url, { method: 'GET', cache: 'no-cache' });
            if (resp.ok) {
                statusDiv.innerText = `✅ ${axisName}轴 → ${angle}°`;
                setTimeout(() => {
                    if (statusDiv.innerText.includes(axisName)) 
                        statusDiv.innerText = "📡 在线，等待指令";
                }, 800);
            } else {
                console.warn(`${axisName}轴 HTTP ${resp.status}`);
            }
        } catch (err) {
            // 不显示错误，避免干扰
            console.error(err);
        }
    }

    // 发送速度指令
    async function sendSpeed(percent) {
        try {
            await fetch(`${BASE_URL}/speed?val=${percent}`, { method: 'GET', cache: 'no-cache' });
        } catch (err) {}
    }

    // 归零：滑块设为各自的机械零点 (A:90, B:0, C:180, G:0)
    async function zeroAll() {
        // 定义零点
        const zeroPos = {A:90, B:0, C:180, G:0};
        for (let axis of ['A','B','C','G']) {
            sliders[axis].value = zeroPos[axis];
            spans[axis].innerText = zeroPos[axis];
            sendAngle(axis, zeroPos[axis]);
        }
        // 发送归零请求
        try {
            const resp = await fetch(`${BASE_URL}/zero`, { method: 'GET', cache: 'no-cache' });
            if (resp.ok) {
                statusDiv.innerText = "🔄 已归零至机械零点 (A90 B0 C180 G0)";
            } else {
                statusDiv.innerText = "🔄 归零指令已发送";
            }
        } catch (err) {
            statusDiv.innerText = "⚠️ 归零请求失败，但滑块已复位";
        }
    }

    // 绑定滑块事件
    for (let axis of ['A','B','C','G']) {
        const slider = sliders[axis];
        const span = spans[axis];
        slider.addEventListener('input', (e) => {
            const val = e.target.value;
            span.innerText = val;
            sendAngle(axis, val);
        });
    }

    speedSlider.addEventListener('input', (e) => {
        const val = e.target.value;
        speedSpan.innerText = val;
        sendSpeed(val);
    });

    zeroBtn.addEventListener('click', zeroAll);

    // 连接检测
    async function checkConnection() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 1500);
            const resp = await fetch(`${BASE_URL}/`, { method: 'HEAD', signal: controller.signal });
            clearTimeout(timeoutId);
            if (resp.ok) {
                statusDiv.innerText = "🟢 已连接 ESP32，拖动滑块即可控制";
            } else {
                statusDiv.innerText = "⚠️ 连接异常，请确保已连接 DolphinArm 热点";
            }
        } catch (err) {
            statusDiv.innerText = "🔌 未检测到 ESP32，请连接热点 192.168.4.1";
        }
    }
    checkConnection();
</script>
</body>
</html>
)rawliteral";

// ========== Web 路由处理 ==========
void handleRoot() {
    server.send(200, "text/html", index_html);
}

void handleSetGesture() {
    if (server.hasArg("servo") && server.hasArg("angle")) {
        gestureMode = true;
        lastGestureCmdMs = millis();

        int id = server.arg("servo").toInt() - 1;
        int angle = server.arg("angle").toInt();

        if (id >= 0 && id < 4) {
            target[id] = constrain(angle, 0, 180);
        }
        server.send(200, "text/plain", "OK");
    } else {
        server.send(400, "text/plain", "Missing servo or angle");
    }
}

void handleSet() {
    gestureMode = false;    // 网页一来，直接抢回控制权
    
    if (server.hasArg("servo") && server.hasArg("angle")) {
        int id = server.arg("servo").toInt() - 1;
        int angle = server.arg("angle").toInt();

        if (id >= 0 && id < 4) {
            target[id] = constrain(angle, 0, 180);
        }
        server.send(200, "text/plain", "OK");
    } else {
        server.send(400, "text/plain", "Missing servo or angle");
    }
}

void handleSpeed() {
    gestureMode = false;
    if (server.hasArg("val")) {
        speedPercent = constrain(server.arg("val").toInt(), 0, 100);
        server.send(200, "text/plain", "Speed = " + String(speedPercent));
    } else {
        server.send(400, "text/plain", "Missing val");
    }
}

void handleZero() {
    // 归零到机械零点
    target[0] = ZERO_A;
    target[1] = ZERO_B;
    target[2] = ZERO_C;
    target[3] = ZERO_G;
    server.send(200, "text/plain", "Zeroed to mechanical zero");
}

void handleMode() {
    if (server.hasArg("mode")) {
        String mode = server.arg("mode");
        if (mode == "gesture") {
            gestureMode = true;
            server.send(200, "text/plain", "Gesture Mode");
        } else if (mode == "web") {
            gestureMode = false;
            server.send(200, "text/plain", "Web Mode");
        }
    }
}

// ========== 初始化 ==========
void setup() {
    Serial.begin(115200);
    servoA.attach(SERVO_A_PIN);
    servoB.attach(SERVO_B_PIN);
    servoC.attach(SERVO_C_PIN);
    servoG.attach(SERVO_G_PIN);

    // 初始化到机械零点
    servoA.write(ZERO_A);
    servoB.write(ZERO_B);
    servoC.write(ZERO_C);
    servoG.write(ZERO_G);
    current[0] = target[0] = ZERO_A;
    current[1] = target[1] = ZERO_B;
    current[2] = target[2] = ZERO_C;
    current[3] = target[3] = ZERO_G;

    WiFi.softAP(ssid, password);
    Serial.print("AP IP: ");
    Serial.println(WiFi.softAPIP());

    server.on("/", handleRoot);
    server.on("/set", handleSet);
    server.on("/speed", handleSpeed);
    server.on("/zero", handleZero);
    server.on("/mode", handleMode);
    server.on("/setGesture", handleSetGesture);
    
    server.begin();
    Serial.println("HTTP server started");
}

// ========== 主循环 ==========
void loop() {
    server.handleClient();
    // 手势超时自动切回网页模式
    if (gestureMode && millis() - lastGestureCmdMs > GESTURE_TIMEOUT_MS) {
        gestureMode = false;
    }
    updateEasing();
}