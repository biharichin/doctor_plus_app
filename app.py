from flask import Flask, render_template, request, session, flash, redirect, url_for, jsonify
import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, timedelta # Import date and timedelta
import uuid # Import uuid for generating unique IDs

load_dotenv() # Load environment variables from .env file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "a_very_secret_key_for_dev") # Use environment variable or a default for development

# Initialize scheduler
scheduler = BackgroundScheduler()

UPLOAD_FOLDER_CERTIFICATES = 'static/uploads/certificates'
UPLOAD_FOLDER_SIGNATURES = 'static/uploads/signatures'
UPLOAD_FOLDER_PHOTOS = 'static/uploads/photos'

# Create upload directories if they don't exist
os.makedirs(UPLOAD_FOLDER_CERTIFICATES, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_SIGNATURES, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_PHOTOS, exist_ok=True)


def get_connection():
    return mysql.connector.connect(
        host="sql12.freesqldatabase.com",
        user="sql12790290",
        password="mJ4BgSXKdz",
        database="sql12790290",
        port=3306
    )

@app.route("/")
def home():
    return render_template("home.html")

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

def check_and_update_expired_profiles():
    with app.app_context():
        conn = get_connection()
        c = conn.cursor()
        try:
            today = date.today()
            # Find profiles that are 'verified' and whose expiry date has passed
            c.execute(
                "UPDATE doctor_profiles SET verification_status = %s, verified_by_university = NULL, verification_expiry_date = NULL WHERE verification_status = %s AND verification_expiry_date <= %s",
                ('expired', 'verified', today)
            )
            conn.commit()
            print(f"Scheduler: Updated {c.rowcount} expired profiles to 'expired' status.")
        except mysql.connector.Error as err:
            print(f"Scheduler Error: Database error during expiry check: {err}")
            conn.rollback()
        except Exception as e:
            print(f"Scheduler Error: An unexpected error during expiry check: {e}")
        finally:
            conn.close()


@app.route("/submit_doctor_profile", methods=["POST"])
def submit_doctor_profile():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Please log in to submit your profile."}), 401

    user_id = session["user_id"]
    conn = get_connection()
    c = conn.cursor()

    try:
        # --- Personal Information ---
        university_name = request.form["university_name"]
        degree_name = request.form["degree_name"]
        specialization = request.form["specialization"]
        experience = request.form["experience"]
        if experience == '':
            experience = None
        address = request.form["address"]
        about = request.form.get("about", "") # Optional field

        # Debugging: Print all collected form data and file info
        print(f"DEBUG: university_name: {university_name}")
        print(f"DEBUG: degree_name: {degree_name}")
        print(f"DEBUG: specialization: {specialization}")
        print(f"DEBUG: experience: {experience}")
        print(f"DEBUG: address: {address}")
        print(f"DEBUG: about: {about}")
        print(f"DEBUG: request.files: {request.files}")

        # Handle file uploads
        degree_certificate_path = None
        if "degree_certificate" in request.files:
            certificate_file = request.files["degree_certificate"]
            if certificate_file.filename != "":
                filename = secure_filename(certificate_file.filename)
                certificate_file.save(os.path.join(UPLOAD_FOLDER_CERTIFICATES, filename))
                degree_certificate_path = os.path.join(UPLOAD_FOLDER_CERTIFICATES, filename)

        signature_path = None
        if "signature" in request.files:
            signature_file = request.files["signature"]
            if signature_file.filename != "":
                filename = secure_filename(signature_file.filename)
                signature_file.save(os.path.join(UPLOAD_FOLDER_SIGNATURES, filename))
                signature_path = os.path.join(UPLOAD_FOLDER_SIGNATURES, filename)

        photo_path = None
        if "photo" in request.files:
            photo_file = request.files["photo"]
            if photo_file.filename != "":
                filename = secure_filename(photo_file.filename)
                photo_file.save(os.path.join(UPLOAD_FOLDER_PHOTOS, filename))
                photo_path = os.path.join(UPLOAD_FOLDER_PHOTOS, filename)

        # Insert into doctor_profiles
        profile_unique_id = str(uuid.uuid4())
        profile_params = (
            user_id, profile_unique_id, university_name, degree_name, degree_certificate_path,
            specialization, signature_path, photo_path, experience, address, about,
            'pending_payment', None, None # Set expiry date and verified_by_university to NULL initially
        )
        print(f"DEBUG: Doctor Profile INSERT params: {profile_params}") # Debug print
        c.execute(
            """
            INSERT INTO doctor_profiles (
                user_id, unique_id, university_name, degree_name, degree_certificate_path,
                specialization, signature_path, photo_path, experience, address, about,
                verification_status, verification_expiry_date, verified_by_university
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            profile_params
        )
        doctor_profile_id = c.lastrowid

        # --- Clinic Information ---
        clinic_count = 0
        for i in range(4): # Check for up to 4 clinics
            clinic_name = request.form.get(f"clinic_name_{i}")
            if clinic_name: # If clinic name exists, assume clinic data is present
                clinic_count += 1
                city = request.form.get(f"clinic_city_{i}")
                area = request.form.get(f"clinic_area_{i}")
                pin_code = request.form.get(f"clinic_pincode_{i}")
                district = request.form.get(f"clinic_district_{i}")

                # Basic validation for clinic fields
                if not all([city, area, pin_code, district]):
                    conn.rollback()
                    return jsonify({"status": "error", "message": f"Missing information for Clinic {i+1}. Please fill all required clinic fields."}), 400

                c.execute(
                    """
                    INSERT INTO doctor_clinics (
                        doctor_profile_id, clinic_name, city, area, pin_code, district
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (doctor_profile_id, clinic_name, city, area, pin_code, district)
                )
        
        if clinic_count == 0:
            conn.rollback()
            return jsonify({"status": "error", "message": "At least one clinic address is required."}), 400

        conn.commit()
        # Instead of redirecting, return a JSON response
        return jsonify({
            "status": "success",
            "message": "Doctor profile registered successfully! Payment required.",
            "university_name": university_name # Pass university name for payment popup
        })
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({"status": "error", "message": f"Database error: {err}"}), 500
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500
    finally:
        conn.close()



@app.route("/createtables")
def create_tables():
    conn = get_connection()
    c = conn.cursor()
    # Drop tables in reverse order of dependency
    c.execute("DROP TABLE IF EXISTS doctor_clinics")
    c.execute("DROP TABLE IF EXISTS doctor_profiles")
    c.execute("DROP TABLE IF EXISTS users")

    # Create tables in order of dependency
    c.execute("""
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            mobile_number VARCHAR(20) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            gender VARCHAR(10),
            password VARCHAR(255) NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE doctor_profiles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNIQUE NOT NULL,
            unique_id VARCHAR(36) UNIQUE NOT NULL, # UUID for unique ID
            university_name VARCHAR(255),
            degree_name VARCHAR(255),
            degree_certificate_path VARCHAR(255),
            specialization VARCHAR(255),
            signature_path VARCHAR(255),
            photo_path VARCHAR(255),
            experience TEXT,
            address TEXT,
            about TEXT,
            verification_status VARCHAR(50) DEFAULT 'pending_registration', # pending_registration, pending_payment, under_verification, verified, expired
            verification_expiry_date DATE,
            verified_by_university VARCHAR(255),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE doctor_clinics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            doctor_profile_id INT NOT NULL,
            clinic_name VARCHAR(255),
            city VARCHAR(100),
            area VARCHAR(255),
            pin_code VARCHAR(20),
            district VARCHAR(100),
            FOREIGN KEY (doctor_profile_id) REFERENCES doctor_profiles(id)
        )
    """)
    conn.commit()
    conn.close()
    return "Tables created successfully!"

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        mobile_number = request.form["mobile_number"]
        email = request.form["email"]
        gender = request.form["gender"]
        password = request.form["password"]
        hashed_password = generate_password_hash(password)

        conn = get_connection()
        c = conn.cursor(dictionary=True)
        
        # Check if mobile number or email already exists
        c.execute("SELECT id FROM users WHERE mobile_number = %s OR email = %s", (mobile_number, email))
        existing_user = c.fetchone()
        if existing_user:
            flash("Mobile number or email already registered. Please use a different one or log in.", "danger")
            conn.close()
            return redirect(url_for("signup"))

        try:
            c.execute("INSERT INTO users (name, mobile_number, email, gender, password) VALUES (%s, %s, %s, %s, %s)",
                      (name, mobile_number, email, gender, hashed_password))
            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except mysql.connector.Error as err:
            flash(f"Error: {err}", "danger")
            conn.rollback()
        finally:
            conn.close()
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile_number = request.form["mobile_number"]
        password = request.form["password"]

        conn = get_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT * FROM users WHERE mobile_number = %s", (mobile_number,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("Login successful!", "success")
            return redirect(url_for("registration_dashboard")) # Redirect to the new registration dashboard
        else:
            flash("Invalid mobile number or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))

@app.route("/forgot_password")
def forgot_password():
    # Placeholder for forgot password functionality
    flash("Forgot password functionality coming soon!", "info")
    return render_template("forgot_password.html")

@app.route("/registration_dashboard")
def registration_dashboard():
    if "user_id" not in session:
        flash("Please log in to access this page.", "warning")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_connection()
    c = conn.cursor(dictionary=True)
    c.execute("SELECT name, mobile_number, email, gender FROM users WHERE id = %s", (user_id,))
    user_data = c.fetchone()

    doctor_profile = None
    doctor_clinics = []

    if user_data:
        # Fetch doctor profile if exists
        c.execute("SELECT * FROM doctor_profiles WHERE user_id = %s", (user_id,))
        doctor_profile = c.fetchone()

        if doctor_profile:
            # Fetch clinics if doctor profile exists
            c.execute("SELECT * FROM doctor_clinics WHERE doctor_profile_id = %s", (doctor_profile['id'],))
            doctor_clinics = c.fetchall()

    conn.close()

    if not user_data:
        flash("User data not found.", "danger")
        return redirect(url_for("logout"))

    return render_template("registration_dashboard.html", user_data=user_data, doctor_profile=doctor_profile, doctor_clinics=doctor_clinics)

@app.route("/update_payment_status", methods=["POST"])
def update_payment_status():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Not logged in."}), 401

    user_id = session["user_id"]
    data = request.get_json()
    new_status = data.get("status")

    if new_status not in ['under_verification', 'pending_payment']:
        return jsonify({"status": "error", "message": "Invalid status provided."}), 400

    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "UPDATE doctor_profiles SET verification_status = %s WHERE user_id = %s",
            (new_status, user_id)
        )
        conn.commit()
        return jsonify({"status": "success", "message": "Verification status updated."})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({"status": "error", "message": f"Database error: {err}"}), 500
    finally:
        conn.close()

@app.route("/admin/verify_profile", methods=["POST"])
def admin_verify_profile():
    # In a real application, this route would be secured with admin authentication
    data = request.get_json()
    unique_id = data.get("unique_id")
    status = data.get("status")
    university_name = data.get("university_name")
    expiry_date_str = data.get("expiry_date") # YYYY-MM-DD format

    if not all([unique_id, status]):
        return jsonify({"status": "error", "message": "Missing unique_id or status."}), 400

    conn = get_connection()
    c = conn.cursor()
    try:
        update_query = "UPDATE doctor_profiles SET verification_status = %s"
        params = [status]

        if status == 'verified':
            if not all([university_name, expiry_date_str]):
                return jsonify({"status": "error", "message": "University name and expiry date are required for 'verified' status."}), 400
            update_query += ", verified_by_university = %s, verification_expiry_date = %s"
            params.extend([university_name, expiry_date_str])
        else:
            # Clear verification details if status is not 'verified'
            update_query += ", verified_by_university = NULL, verification_expiry_date = NULL"

        update_query += " WHERE unique_id = %s"
        params.append(unique_id)

        c.execute(update_query, tuple(params))
        conn.commit()
        return jsonify({"status": "success", "message": f"Profile {unique_id} verification status updated to {status}."})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({"status": "error", "message": f"Database error: {err}"}), 500
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    # Add the job to the scheduler
    scheduler.add_job(check_and_update_expired_profiles, 'interval', minutes=1) # Runs every 1 minute for testing
    scheduler.start()

    # For Render.com hosting
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
