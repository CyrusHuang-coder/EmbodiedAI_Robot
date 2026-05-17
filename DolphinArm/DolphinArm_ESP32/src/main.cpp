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
const int ZERO_B = 10;
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

// ========== 机械安全限幅（根据实测） ==========
const int MIN_ANGLE[4] = {20,   0,   0,   0};   // A,B,C,G 下限
const int MAX_ANGLE[4] = {160, 110, 180, 85};   // 上限

int getStepDelay() {
    // 速度0% -> 200ms, 100% -> BASE_STEP_DELAY_MS
    int delayMs = map(speedPercent, 0, 100, BASE_STEP_DELAY_MS * 40, BASE_STEP_DELAY_MS);
    return constrain(delayMs, BASE_STEP_DELAY_MS, 200);
}

// 非阻塞平滑（去掉 delay）
unsigned long lastStepTime = 0;
void updateEasing() {
    if (millis() - lastStepTime < getStepDelay()) return;
    lastStepTime = millis();

    bool changed = false;
    for (int i = 0; i < 4; i++) {
        if (current[i] != target[i]) {
            int step = (target[i] > current[i]) ? 1 : -1;
            current[i] += step;
            current[i] = constrain(current[i], MIN_ANGLE[i], MAX_ANGLE[i]);
            changed = true;
        }
    }
    if (changed) {
        servoA.write(current[0]);
        servoB.write(current[1]);
        servoC.write(current[2]);
        servoG.write(current[3]);
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>海豚机械臂</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: system-ui, sans-serif; background: #f0f4f8; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { max-width: 550px; width: 100%; background: white; border-radius: 32px; padding: 24px 20px 32px; box-shadow: 0 8px 20px rgba(0,0,0,0.1); text-align: center; }
        h1 { font-size: 1.8rem; color: #1e2f5e; margin: 0 0 0.5rem; }
        .slider-group { margin: 20px 0; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .slider-group label { font-weight: 600; width: 70px; text-align: left; color: #1f3a6b; }
        input[type="range"] { flex: 2; min-width: 180px; height: 6px; border-radius: 10px; background: #d0ddeb; appearance: none; }
        input[type="range"]::-webkit-slider-thumb { width: 20px; height: 20px; background: #2c7da0; border-radius: 50%; cursor: pointer; border: 2px solid white; }
        .value { width: 52px; background: #eef2f7; border-radius: 30px; padding: 4px 0; font-weight: bold; color: #0059b3; }
        button { background: #2c7da0; border: none; color: white; font-size: 1rem; font-weight: 600; padding: 10px 24px; border-radius: 40px; margin: 12px 8px 0; cursor: pointer; }
        button:hover { background: #1f5e7a; }
        .status { margin-top: 20px; font-size: 0.8rem; color: #2c7da0; background: #e9f0f5; padding: 8px; border-radius: 28px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🐬 海豚机械臂</h1>
    <div class="slider-group"><label>基座(A)</label><input type="range" id="jointA" min="20" max="160" value="90" step="5"><span class="value" id="valA">90</span></div>
    <div class="slider-group"><label>肩(B)</label><input type="range" id="jointB" min="0" max="110" value="10" step="5"><span class="value" id="valB">10</span></div>
    <div class="slider-group"><label>肘(C)</label><input type="range" id="jointC" min="0" max="180" value="180" step="5"><span class="value" id="valC">180</span></div>
    <div class="slider-group"><label>夹爪(G)</label><input type="range" id="jointG" min="0" max="85" value="0" step="5"><span class="value" id="valG">0</span></div>
    <div class="slider-group"><label>速度</label><input type="range" id="speed" min="10" max="100" value="70" step="5"><span class="value" id="speedVal">70</span></div>
    <div><button id="zeroBtn">🔄 安全归零</button></div>
    <div class="status" id="statusMsg">⚡ 等待连接...</div>
</div>
<script>
    const BASE_URL = "http://192.168.4.1";
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
    const statusDiv = document.getElementById('statusMsg');

    const nameToId = {A:1, B:2, C:3, G:4};
    let sendTimer = {};

    // 防抖发送：停止拖动 150ms 后才发送
    function sendAngle(axis, angle) {
        clearTimeout(sendTimer[axis]);
        sendTimer[axis] = setTimeout(() => {
            const servoId = nameToId[axis];
            fetch(`${BASE_URL}/set?servo=${servoId}&angle=${angle}`, { method: 'GET', cache: 'no-cache' })
                .then(r => {
                    if(r.ok) statusDiv.innerText = `✅ ${axis}轴 → ${angle}°`;
                })
                .catch(() => {});
        }, 150);
    }

    function sendSpeed(val) {
        fetch(`${BASE_URL}/speed?val=${val}`, { method: 'GET', cache: 'no-cache' }).catch(()=>{});
    }

    // 归零到安全零点 (A:90, B:10, C:180, G:0)
    async function zeroAll() {
        const zeroPos = {A:90, B:10, C:180, G:0};
        for (let axis of ['A','B','C','G']) {
            sliders[axis].value = zeroPos[axis];
            spans[axis].innerText = zeroPos[axis];
            // 只发请求，不等结果（用 fetch 然后 catch，不 await）
            fetch(`${BASE_URL}/set?servo=${nameToId[axis]}&angle=${zeroPos[axis]}`, { method: 'GET' })
                .catch(() => {});
        }
        statusDiv.innerText = "🔄 已归零至安全零点";
    }

    // 实时同步 ESP32 角度（每 200ms）
    async function syncAngles() {
        try {
            const resp = await fetch(`${BASE_URL}/status`, { cache: 'no-cache' });
            if (resp.ok) {
                const data = await resp.json();
                for (let axis of ['A','B','C','G']) {
                    const angle = data[axis];
                    sliders[axis].value = angle;
                    spans[axis].innerText = angle;
                }
                statusDiv.innerText = "🟢 在线，角度已同步";
            }
        } catch(e) {}
    }

    for (let axis of ['A','B','C','G']) {
        const slider = sliders[axis];
        slider.addEventListener('input', (e) => {
            const val = e.target.value;
            spans[axis].innerText = val;
            sendAngle(axis, val);
        });
    }
    speedSlider.addEventListener('input', (e) => {
        speedSpan.innerText = e.target.value;
        sendSpeed(e.target.value);
    });
    document.getElementById('zeroBtn').addEventListener('click', zeroAll);

    syncAngles();
    setInterval(syncAngles, 200);
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
            int limited = constrain(angle, MIN_ANGLE[id], MAX_ANGLE[id]);
            if (target[id] != limited) target[id] = limited;   // 防重复
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
            int limited = constrain(angle, MIN_ANGLE[id], MAX_ANGLE[id]);
            if (target[id] != limited) target[id] = limited;
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

// 新增：状态接口，返回当前角度 JSON
void handleStatus() {
    String json = "{";
    json += "\"A\":" + String(current[0]) + ",";
    json += "\"B\":" + String(current[1]) + ",";
    json += "\"C\":" + String(current[2]) + ",";
    json += "\"G\":" + String(current[3]);
    json += "}";
    server.send(200, "application/json", json);
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
    server.on("/status", handleStatus);   // 新增状态接口
    
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