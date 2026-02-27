#!/bin/bash
# Linux Memory Self-Heal Script
# Monitors memory usage and takes corrective action

THRESHOLD=85
LOG="/var/log/memory-heal.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

get_memory_usage() {
    free | awk '/Mem:/ {printf "%.0f", ($3/$2) * 100}'
}

clear_cache() {
    log "Clearing page cache, dentries, and inodes"
    sync
    echo 3 > /proc/sys/vm/drop_caches
}

kill_top_consumer() {
    local pid=$(ps aux --sort=-%mem | awk 'NR==2 {print $2}')
    local name=$(ps aux --sort=-%mem | awk 'NR==2 {print $11}')
    log "Killing top memory consumer: $name (PID: $pid)"
    kill -15 "$pid"
    sleep 2
    kill -9 "$pid" 2>/dev/null
}

usage=$(get_memory_usage)
log "Memory usage: ${usage}%"

if [ "$usage" -ge "$THRESHOLD" ]; then
    log "Memory usage above ${THRESHOLD}% threshold"
    
    clear_cache
    sleep 2
    
    usage=$(get_memory_usage)
    log "Memory usage after cache clear: ${usage}%"
    
    if [ "$usage" -ge "$THRESHOLD" ]; then
        kill_top_consumer
        usage=$(get_memory_usage)
        log "Memory usage after kill: ${usage}%"
    fi
    
    log "Healing complete"
else
    log "Memory usage normal"
fi
