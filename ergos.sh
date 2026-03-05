#!/bin/bash
# Ergos start/stop script — manages server + Flutter client
set -euo pipefail

ERGOS_DIR="$HOME/ergos-mvp"
CLIENT_DIR="$ERGOS_DIR/client"
FLUTTER="$HOME/flutter/bin/flutter"
LOG="/tmp/ergos-server.log"
PID_FILE="$HOME/.ergos/server.pid"

start() {
    # Check if already running
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Server already running (PID $(cat "$PID_FILE"))"
    else
        echo "Starting Ergos server..."
        cd "$ERGOS_DIR"
        source .venv/bin/activate
        nohup ergos start > "$LOG" 2>&1 &
        sleep 2
        if [ -f "$PID_FILE" ]; then
            echo "Server started (PID $(cat "$PID_FILE")), log: $LOG"
        else
            echo "Server may still be loading models. Check: tail -f $LOG"
        fi
    fi

    echo "Starting Flutter client..."
    cd "$CLIENT_DIR"
    $FLUTTER run -d all &>/dev/null &
    echo "Client launching in background"
}

stop() {
    # Stop Flutter
    echo "Stopping Flutter client..."
    pkill -f "flutter run" 2>/dev/null || true
    pkill -f "flutter_tool" 2>/dev/null || true

    # Stop server
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        echo "Stopping Ergos server (PID $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 1
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
        rm -f "$PID_FILE"
    else
        # Fallback: find by process name
        pkill -f "ergos start" 2>/dev/null || true
    fi
    echo "Ergos stopped"
}

restart() {
    stop
    sleep 2
    start
}

logs() {
    tail -f "$LOG"
}

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    logs)    logs ;;
    *)
        echo "Usage: ergos-ctl {start|stop|restart|logs}"
        ;;
esac
