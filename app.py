from flask import Flask, send_file, jsonify
import os

app = Flask(__name__)

# Hii inarudisha DEX file halisi
@app.route('/payload.dex')
def serve_dex():
    try:
        return send_file('payload.dex', 
                        mimetype='application/vnd.android.dex',
                        as_attachment=False,
                        download_name='payload.dex')
    except Exception as e:
        return jsonify({'error': str(e)}), 404

# Hii inarudisha version
@app.route('/version')
def serve_version():
    return '1.0.0'

# Root inarudisha info
@app.route('/')
def index():
    return jsonify({
        'endpoints': {
            'payload': '/payload.dex',
            'version': '/version'
        },
        'status': 'online'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
