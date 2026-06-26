# Requires Run as Administrator
Write-Host "Applying Mosquitto Configuration Fixes..."

# 1. Update mosquitto.conf
$confPath = "C:\Program Files\mosquitto\mosquitto.conf"
if (Test-Path $confPath) {
    Add-Content -Path $confPath -Value "`nlistener 1883 0.0.0.0`nallow_anonymous true"
    Write-Host "Successfully updated mosquitto.conf"
} else {
    Write-Host "Warning: Could not find mosquitto.conf at $confPath"
}

# 2. Add Windows Firewall Rule
Write-Host "Adding Windows Firewall rule for Port 1883..."
New-NetFirewallRule -DisplayName "MQTT Broker (Port 1883)" -Direction Inbound -LocalPort 1883 -Protocol TCP -Action Allow | Out-Null

# 3. Restart Mosquitto Service
Write-Host "Restarting Mosquitto Service..."
Restart-Service mosquitto
Write-Host "Done! Your ESP32 should now be able to connect."
Read-Host -Prompt "Press Enter to exit"
