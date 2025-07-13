from flask import Flask, render_template, request
import mysql.connector
import os
from werkzeug.utils import secure_filename


app = Flask(__name__)
def get_connection():
    return mysql.connector.connect(
        host="sql12.freesqldatabase.com",
        user="sql12789576",
        password="svgwzPG2NJ",
        database="sql12789576",
        port=3306
    )

@app.route("/")
def home():
    return render_template("doctor_form.html")

@app.route("/submit", methods=["POST"])
def submit_doctor():
    name = request.form["name"]
    age = request.form["age"]
    gender = request.form["gender"]
    specialty = request.form["specialty"]
    city = request.form["city"]
    photo = request.files["photo"]
    filename = secure_filename(photo.filename)
    photo.save(os.path.join("static/photos", filename))


    conn = get_connection()
    c = conn.cursor()

    c.execute("INSERT INTO doctors (name, age, gender, specialty, city, photo) VALUES (%s, %s, %s, %s, %s, %s)",
              (name, age, gender, specialty, city, filename))

    conn.commit()
    conn.close()

    return "Doctor added successfully!"


if __name__ == "__main__":
    app.run(debug=True)
# For Render.com hosting
port = int(os.environ.get("PORT", 5000))
app.run(host='0.0.0.0', port=port)
