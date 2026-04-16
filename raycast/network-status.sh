#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Network Status
# @raycast.mode fullOutput
# @raycast.packageName Network Monitor
# @raycast.description Check network connection status, ping, Wi-Fi signal, and speed

echo "🌐 Network Status Report"
echo "========================"
echo ""

# Get current timestamp
echo "📅 Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Check internet connection and measure latency
echo "🔌 Internet Connection:"
latency_sec=$(curl -s -o /dev/null -w "%{time_total}" -X HEAD --connect-timeout 3 "https://www.gstatic.com/generate_204")
curl_exit=$?

if [ $curl_exit -eq 0 ] && [ ! -z "$latency_sec" ]; then
    echo "✅ Connected to internet"
    echo ""
    
    # Calculate latency in milliseconds
    latency_ms=$(echo "$latency_sec" | awk '{printf "%.0f", $1 * 1000}')
    
    echo "🏓 Latency Test (gstatic.com):"
    echo "   Time: ${latency_ms} ms"
else
    echo "❌ No internet connection"
    exit 1
fi
echo ""

# Wi-Fi information
echo "📶 Wi-Fi Information:"
# Get Wi-Fi interface name
wifi_interface=$(networksetup -listallhardwareports 2>/dev/null | grep -A 1 "Wi-Fi" | grep "Device" | awk '{print $2}')
if [ ! -z "$wifi_interface" ]; then
    echo "   Interface: $wifi_interface"
    
    # Check if we have an IP address on Wi-Fi interface
    wifi_ip=$(ifconfig "$wifi_interface" 2>/dev/null | grep "inet " | awk '{print $2}')
    if [ ! -z "$wifi_ip" ]; then
        echo "   IP Address: $wifi_ip"
        
        # Get Wi-Fi info using system_profiler (no sudo required)
        if command -v system_profiler &> /dev/null; then
            wifi_info=$(system_profiler SPAirPortDataType 2>/dev/null)
            if [ ! -z "$wifi_info" ]; then
                # Extract current network name from Current Network Information
                current_network=$(echo "$wifi_info" | awk '/Current Network Information:/,/Other Local Wi-Fi Networks:/' | grep -v "Other Local Wi-Fi Networks:" | grep -E "^[[:space:]]*[A-Za-z0-9_-]+:$" | head -1 | sed 's/://' | sed 's/^[[:space:]]*//')
                if [ ! -z "$current_network" ]; then
                    echo "   Network: $current_network"
                fi
                
                # Extract signal strength (better parsing)
                signal_line=$(echo "$wifi_info" | grep "Signal / Noise:" | head -1)
                if [ ! -z "$signal_line" ]; then
                    signal_value=$(echo "$signal_line" | awk '{print $3}' | sed 's/dBm//')
                    if [[ "$signal_value" =~ ^-?[0-9]+$ ]]; then
                        # Convert RSSI to signal bars (approximate)
                        if [ "$signal_value" -ge -50 ]; then
                            signal_bars="█████ (Excellent)"
                        elif [ "$signal_value" -ge -60 ]; then
                            signal_bars="████  (Good)"
                        elif [ "$signal_value" -ge -70 ]; then
                            signal_bars="███   (Fair)"
                        elif [ "$signal_value" -ge -80 ]; then
                            signal_bars="██    (Poor)"
                        else
                            signal_bars="█     (Very Poor)"
                        fi
                        echo "   Signal: $signal_bars (RSSI: ${signal_value} dBm)"
                    fi
                fi
                
                # Extract transmit rate
                tx_rate=$(echo "$wifi_info" | grep "Transmit Rate:" | head -1 | awk '{print $3}')
                if [ ! -z "$tx_rate" ]; then
                    echo "   Speed: $tx_rate Mbps"
                fi
                
                # Extract channel (better parsing)
                channel_line=$(echo "$wifi_info" | grep "Channel:" | head -1)
                if [ ! -z "$channel_line" ]; then
                    channel_num=$(echo "$channel_line" | awk '{print $2}' | sed 's/,//')
                    channel_freq=$(echo "$channel_line" | awk '{print $3, $4}' | sed 's/,//')
                    if [ ! -z "$channel_num" ] && [ ! -z "$channel_freq" ]; then
                        echo "   Channel: $channel_num ($channel_freq)"
                    fi
                fi
                
                # Extract MCS Index for additional speed info
                mcs_index=$(echo "$wifi_info" | grep "MCS Index:" | head -1 | awk '{print $3}')
                if [ ! -z "$mcs_index" ]; then
                    echo "   MCS Index: $mcs_index"
                fi
                
                # Extract security
                security=$(echo "$wifi_info" | grep "Security:" | head -1 | awk '{print $2, $3}')
                if [ ! -z "$security" ]; then
                    echo "   Security: $security"
                fi
                
                # Extract PHY Mode
                phy_mode=$(echo "$wifi_info" | grep "PHY Mode:" | head -1 | awk '{print $3}')
                if [ ! -z "$phy_mode" ]; then
                    echo "   PHY Mode: $phy_mode"
                fi
            fi
        else
            # Fallback to basic network info
            wifi_info=$(networksetup -getinfo "Wi-Fi" 2>/dev/null)
            if [ ! -z "$wifi_info" ]; then
                router=$(echo "$wifi_info" | grep "Router:" | awk '{print $2}')
                if [ ! -z "$router" ]; then
                    echo "   Router: $router"
                fi
                echo "   Network: Connected (basic info only)"
            fi
        fi
    else
        echo "   Not connected to Wi-Fi"
    fi
else
    echo "   Wi-Fi interface not found"
fi
echo ""

# Network speed test (basic)
echo "⚡ Network Speed Test:"
echo "   Testing download speed..."
# Use curl to download a small file and measure time
start_time=$(date +%s.%N)
curl -s -o /dev/null --max-time 10 https://httpbin.org/bytes/1024
end_time=$(date +%s.%N)
if [ $? -eq 0 ]; then
    duration=$(echo "$end_time - $start_time" | bc -l 2>/dev/null)
    if [ ! -z "$duration" ] && [ "$duration" != "0" ]; then
        speed_kbps=$(echo "scale=2; 8 / $duration" | bc -l 2>/dev/null)
        echo "   Download: ${speed_kbps} Mbps (1KB in ${duration}s)"
    else
        echo "   Speed test completed (time measurement failed)"
    fi
else
    echo "   Speed test failed"
fi
echo ""

# Network interface information
echo "🔧 Network Interfaces:"
if command -v ifconfig &> /dev/null; then
    active_interfaces=$(ifconfig | grep -E "^[a-zA-Z0-9]+:" | grep -v "lo0" | awk '{print $1}' | sed 's/://')
    for interface in $active_interfaces; do
        if [ "$interface" != "" ]; then
            ip_addr=$(ifconfig "$interface" | grep "inet " | awk '{print $2}')
            if [ ! -z "$ip_addr" ]; then
                echo "   $interface: $ip_addr"
            fi
        fi
    done
else
    echo "   ifconfig command not available"
fi
echo ""

# DNS information
echo "🌍 DNS Information:"
if command -v scutil &> /dev/null; then
    dns_servers=$(scutil --dns | grep "nameserver\[" | head -3 | awk '{print $3}')
    if [ ! -z "$dns_servers" ]; then
        echo "   Primary DNS: $(echo "$dns_servers" | head -1)"
        echo "   Secondary DNS: $(echo "$dns_servers" | head -2 | tail -1)"
    else
        echo "   DNS servers not found"
    fi
else
    echo "   scutil command not available"
fi
echo ""

# Additional network info
echo "📊 Additional Information:"
# Check if we're on VPN
if command -v scutil &> /dev/null; then
    vpn_status=$(scutil --nc list | grep "Connected" | head -1)
    if [ ! -z "$vpn_status" ]; then
        echo "   VPN: Connected"
    else
        echo "   VPN: Not connected"
    fi
fi

# Check network location
if command -v scselect &> /dev/null; then
    current_location=$(scselect 2>/dev/null | grep "*" | sed 's/^[[:space:]]*//')
    if [ ! -z "$current_location" ]; then
        echo "   Network Location: $current_location"
    fi
fi

echo ""
echo "✅ Network status check completed!"
