from flask import Flask, send_file, jsonify
import os

app = Flask(__name__)

# Route to serve the DEX file
@app.route('/payload.dex')
def serve_dex():
    # Check if file exists
    if os.path.exists('payload.dex'):
        return send_file('payload.dex', as_attachment=False)
    else:
        return jsonify({"error": "DEX file not found"}), 404

# Route to check version
@app.route('/version')
def version():
    return "1.0.0"

# Root route
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "endpoints": {
            "payload": "/payload.dex",
            "version": "/version"
        }
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
