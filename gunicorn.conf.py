import os

bind = "0.0.0.0:" + os.getenv("PORT", "8000")
workers = 1
control_socket_disable = True
loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"
