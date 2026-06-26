#include <WiFi.h>
#include <Firebase_ESP_Client.h>
#include "DHT.h"
#include <PZEM004Tv30.h>
#include <PubSubClient.h>

// Helper headers for background authentication and token recycling
#include <addons/TokenHelper.h>
#include <addons/RTDBHelper.h>

// ======================== CONFIGURATION ZONE ========================
#define WIFI_SSID "NPAYYA-2.4G"
#define WIFI_PASSWORD "9448529877"

#define FIREBASE_HOST "smart-power-meter-873a6-default-rtdb.firebaseio.com" 
#define FIREBASE_API_KEY "AIzaSyDH41ABgPFEnBt9UKp4Fr8B5SmCdn8TF_0"
#define USER_EMAIL "test@gmail.com"
#define USER_PASSWORD "Password2005"

#define MQTT_SERVER "192.168.1.33" // Your laptop IP
#define MQTT_PORT 1883
#define MQTT_TOPIC "solar/telemetry"
// ====================================================================

// Hardware Pin Specifications
const int LDR_PIN = 34;
const int DHT_PIN = 4;
#define PZEM_RX_PIN 16
#define PZEM_TX_PIN 17

// Instantiations
#define DHTTYPE DHT11
DHT dht(DHT_PIN, DHTTYPE);
PZEM004Tv30 pzem(Serial2, PZEM_RX_PIN, PZEM_TX_PIN);

// Cloud Clients
FirebaseData fbdo;
FirebaseAuth auth;
FirebaseConfig config;
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Timing & Event Control
unsigned long prevMillis = 0;
const unsigned long pollInterval = 2000;      // Read sensors every 2 seconds
const unsigned long heartbeatInterval = 30000; // Guaranteed update every 30 seconds
unsigned long lastUpdateMillis = 0;

// State Tracking for Event-Driven Logic
float lastSentVoltage = -999.0;
float lastSentPower = -999.0;
float lastSentLight = -999.0;

// Event Thresholds
const float VOLTAGE_THRESHOLD = 2.0; // Volts
const float POWER_THRESHOLD = 5.0;   // Watts
const float LIGHT_THRESHOLD = 5.0;   // Percentage

void initWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi network");
  
  int timeoutCounter = 0;
  while (WiFi.status() != WL_CONNECTED && timeoutCounter < 20) {
    delay(500);
    Serial.print(".");
    timeoutCounter++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[Wi-Fi] Connected successfully!");
    Serial.print("[Wi-Fi] Local IP: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[Wi-Fi] Connection timed out. Will retry in loop.");
  }
}

void reconnectMQTT() {
  if (!mqttClient.connected()) {
    Serial.print("[MQTT] Attempting connection...");
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" (Will fallback to Firebase if ready)");
    }
  }
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  pinMode(LDR_PIN, INPUT);
  dht.begin();

  initWiFi();

  // Firebase Setup
  config.api_key = FIREBASE_API_KEY;
  auth.user.email = USER_EMAIL;
  auth.user.password = USER_PASSWORD;
  config.database_url = FIREBASE_HOST;
  config.token_status_callback = tokenStatusCallback; 
  
  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);

  // MQTT Setup
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setBufferSize(1024); // NEW: Increase buffer size for large JSON payloads
  
  Serial.println("[SYSTEM] Setup complete. Awaiting connections...");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    delay(2000);
    return; // Don't try anything without WiFi
  }

  // Attempt to maintain MQTT connection (Primary Route)
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();

  // Polling loop
  if (millis() - prevMillis >= pollInterval || prevMillis == 0) {
    prevMillis = millis();

    // 1. Read Sensors
    int ldrRawValue = analogRead(LDR_PIN);
    float lightPercentage = ((4095-ldrRawValue) / 4095.0) * 100.0;
    
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();
    
    float voltageAC = pzem.voltage();
    float current   = pzem.current();
    float power     = pzem.power();
    float energy    = pzem.energy();
    float frequency = pzem.frequency();
    float pf        = pzem.pf();

    // Handle initial unpowered state gracefully
    if (isnan(voltageAC)) voltageAC = 0;
    if (isnan(power)) power = 0;

    // 2. Evaluate if an Event occurred
    bool eventTriggered = false;
    
    // Check Thresholds
    if (abs(voltageAC - lastSentVoltage) > VOLTAGE_THRESHOLD) eventTriggered = true;
    if (abs(power - lastSentPower) > POWER_THRESHOLD) eventTriggered = true;
    if (abs(lightPercentage - lastSentLight) > LIGHT_THRESHOLD) eventTriggered = true;
    
    // Check Heartbeat
    if (millis() - lastUpdateMillis > heartbeatInterval) {
      eventTriggered = true;
      Serial.println("[EVENT] Triggered by Heartbeat Timer (30s)");
    }

    // 3. Publish if Event Triggered
    if (eventTriggered) {
      Serial.println("\n[EVENT] Significant change detected. Preparing data...");

      FirebaseJson json;
      json.set("environment/light_intensity", lightPercentage);
      if (!isnan(humidity) && !isnan(temperature)) {
        json.set("environment/temperature", temperature);
        json.set("environment/humidity", humidity);
      }
      if (voltageAC > 0) {
        json.set("electrical/voltage", voltageAC);
        json.set("electrical/current", current);
        json.set("electrical/power", power);
        json.set("electrical/energy", energy);
        json.set("electrical/frequency", frequency);
        json.set("electrical/power_factor", pf);
      }

      bool success = false;

      // ROUTING LOGIC: MQTT Primary, Firebase Fallback
      if (mqttClient.connected()) {
        Serial.println("[ROUTE] MQTT connected. Publishing locally...");
        String jsonString;
        json.toString(jsonString, true); 
        
        if (mqttClient.publish(MQTT_TOPIC, jsonString.c_str())) {
          Serial.println("[SUCCESS] Published via MQTT.");
          success = true;
        } else {
          Serial.println("[ERROR] MQTT Publish failed. Attempting Firebase fallback...");
        }
      } 
      
      if (!success) {
        // Fallback to Firebase
        if (Firebase.ready()) {
          Serial.println("[ROUTE] MQTT unavailable. Publishing via Firebase Fallback...");
          if (Firebase.RTDB.setJSON(&fbdo, "/telemetry", &json)) {
            Serial.println("[SUCCESS] Published via Firebase.");
            success = true;
          } else {
            Serial.println(String("[ERROR] Firebase failed: ") + fbdo.errorReason());
          }
        } else {
          Serial.println("[ERROR] Firebase not ready for fallback.");
        }
      }

      // Update State if transmission was successful
      if (success) {
        lastSentVoltage = voltageAC;
        lastSentPower = power;
        lastSentLight = lightPercentage;
        lastUpdateMillis = millis();
      }
    }
  }
}
