# Serve DEX directly - no compilation needed
@app.route('/payload.dex')
def serve_payload_dex():
    """Serve the pre-compiled payload.dex file"""
    try:
        if os.path.exists(PAYLOAD_DEX_FILE):
            return send_file(
                PAYLOAD_DEX_FILE,
                as_attachment=True,
                download_name="payload.dex",
                mimetype="application/octet-stream"
            )
        else:
            # Generate DEX if not exists
            create_valid_dex()
            return send_file(
                PAYLOAD_DEX_FILE,
                as_attachment=True,
                download_name="payload.dex",
                mimetype="application/octet-stream"
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
