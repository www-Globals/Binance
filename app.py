from flask import Flask, send_file, jsonify
import os

app = Flask(__name__)

@app.route('/payload.dex')
def serve_payload():
    if os.path.exists('payload.dex'):
        return send_file('payload.dex', as_attachment=False)
    return jsonify({'error': 'File not found'}), 404

@app.route('/')
def home():
    return jsonify({
        'status': 'online',
        'endpoints': {
            'payload': '/payload.dex',
            'version': '/version'
        }
    })

@app.route('/version')
def version():
    return jsonify({'version': '1.0.0', 'last_updated': '2026-07-13'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
