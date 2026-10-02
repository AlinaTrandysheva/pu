import os
from datetime import datetime

from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
)

db = SQLAlchemy(app)


class Visit(db.Model):
    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)
    visit_time = db.Column(db.DateTime, nullable=False)
    ip_address = db.Column(db.String(100), nullable=False)


with app.app_context():
    db.create_all()


@app.route("/hello", methods=["GET"])
def hello():
    visit = Visit(
        visit_time=datetime.now(),
        ip_address=request.remote_addr
    )

    db.session.add(visit)
    db.session.commit()

    return "Hello", 200