from pyngrok import ngrok
from base import app
import os

if __name__ == '__main__':
    ngrok.set_auth_token("39KWOjEbDyA3A1lGxjeboLbjkXJ_7KjDLkPEvSiYGu4ZJEob8")

    # Only run ngrok in the main process (not Flask reloader child)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        try:
            ngrok.kill()  # Kill any leftover ngrok processes
        except Exception:
            pass

        public_url = ngrok.connect(5000)
        print(f" Public ngrok URL: {public_url}")
        app.config["BASE_URL"] = public_url

    app.run(debug=True, host='0.0.0.0', port=5000)