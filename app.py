import os
from gevent import monkey
monkey.patch_all()
import time
from pyngrok import ngrok
from base import app, socketio

if __name__ == '__main__':
    PORT = 5050

    # ngrok.set_auth_token("39KWOjEbDyA3A1lGxjeboLbjkXJ_7KjDLkPEvSiYGu4ZJEob8")
    #
    # # Kill all existing ngrok tunnels cleanly
    # try:
    #     for tunnel in ngrok.get_tunnels():
    #         ngrok.disconnect(tunnel.public_url)
    #         print(f"🔌 Disconnected tunnel: {tunnel.public_url}")
    # except Exception:
    #     pass
    #
    # try:
    #     ngrok.kill()
    #     time.sleep(2)  # Wait for port release
    # except Exception:
    #     pass
    #
    # # Start fresh tunnel
    # try:
    #     public_url = ngrok.connect(PORT)
    #     print(f"🌍 Public ngrok URL: {public_url}")
    #     app.config["BASE_URL"] = str(public_url)
    # except Exception as e:
    #     print(f"⚠️ ngrok failed: {e} — running without public URL")

    # Run app — socketio.run replaces app.run entirely
    socketio.run(
        app,
        host='0.0.0.0',
        port=PORT,
        debug=True,
        use_reloader=False,
        log_output=True
    )
