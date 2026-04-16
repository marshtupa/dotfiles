#!/bin/bash

# Required parameters:
# @raycast.icon ✅
# @raycast.schemaVersion 1
# @raycast.title Network Status
# @raycast.mode silent
# @raycast.packageName Network Monitor
# @raycast.description Check network connection status, ping, Wi-Fi signal, and speed

# Check internet connection and measure latency
latency_sec=$(curl -s -o /dev/null -w "%{time_total}" -X HEAD --connect-timeout 3 "https://www.gstatic.com/generate_204")
curl_exit=$?

if [ $curl_exit -eq 0 ] && [ ! -z "$latency_sec" ]; then
    # Calculate latency in milliseconds
    latency_ms=$(echo "$latency_sec" | awk '{printf "%.0f", $1 * 1000}')

    echo "Connected in ${latency_ms} ms"
else
    echo "❌ No internet connection"
    exit 1
fi
echo ""
