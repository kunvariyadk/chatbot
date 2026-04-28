# ============================================
# GUNICORN CONFIGURATION
# For Flask + Flask-SocketIO + Gevent
# ============================================
import os
import multiprocessing

# ============================================
# SERVER SOCKET
# ============================================
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
backlog = 2048

# ============================================
# WORKER PROCESSES
# ⚠️ MUST use gevent worker for SocketIO
# ============================================
worker_class = "gevent"
workers = 1  # SocketIO requires exactly 1 worker (unless using Redis message queue)
worker_connections = 1000
threads = 1

# ============================================
# TIMEOUTS
# ============================================
timeout = 120  # Kill worker if silent for 120s
keepalive = 5  # Keep connection alive for 5s
graceful_timeout = 30  # Time to finish requests on shutdown

# ============================================
# LOGGING
# ============================================
accesslog = "/var/log/chatbot/gunicorn-access.log"
errorlog = "/var/log/chatbot/gunicorn-error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# ============================================
# PROCESS NAMING
# ============================================
proc_name = "chatbot_panel"

# ============================================
# SECURITY
# ============================================
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190


# ============================================
# SERVER HOOKS (lifecycle events)
# ============================================
def on_starting(server):
    print("🚀 Gunicorn is starting...")


def on_exit(server):
    print("🛑 Gunicorn is shutting down...")


def worker_exit(server, worker):
    print(f"⚠️  Worker {worker.pid} exited")


def post_fork(server, worker):
    print(f"✅ Worker {worker.pid} spawned")
