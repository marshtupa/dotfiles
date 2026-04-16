#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title ping
# @raycast.mode fullOutput
# @raycast.packageName network
# @raycast.description Check internet connection

echo "Pinging gstatic.com using curl"
echo ""

success=0
total=100

for ((i=1; i<=total; i++)); do
    latency_sec=$(curl -s -o /dev/null -w "%{time_total}" -X HEAD --connect-timeout 2 "https://www.gstatic.com/generate_204")
    if [ $? -eq 0 ] && [ ! -z "$latency_sec" ]; then
        latency_ms=$(echo "$latency_sec" | awk '{printf "%.2f", $1 * 1000}')
        echo "Reply from gstatic.com: time=${latency_ms} ms"
        ((success++))
    else
        echo "Request timeout"
    fi
    sleep 1
done

echo ""
echo "--- gstatic.com ping statistics ---"
loss=$(awk "BEGIN {print (($total - $success) / $total) * 100}")
echo "$total requests transmitted, $success received, ${loss}% request loss"
