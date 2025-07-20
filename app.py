from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from flask_cors import CORS
import qrcode
import io
import base64
import datetime
import sqlite3
from flask import request
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import json
import os
 
app = Flask(__name__)
CORS(app)

app.config["MONGO_URI"] = "mongodb://localhost:27017/counterfeit_db"
mongo = PyMongo(app)
db = mongo.db

def generate_qr_code(data):
    img = qrcode.make(data)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return qr_code_b64

conn = sqlite3.connect('products.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    batch_number TEXT,
    production_date TEXT
)
''')

conn.commit()
conn.close()


@app.route('/register-product', methods=['POST'])
def register_product():
    data = request.get_json()

    product_id = data.get("product_id")
    name = data.get("name")
    manufacturer = data.get("manufacturer")
    batch_number = data.get("batch_number")
    production_date = data.get("production_date")

    try:
        conn = sqlite3.connect('products.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (product_id, name, manufacturer, batch_number, production_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (product_id, name, manufacturer, batch_number, production_date))
        conn.commit()
        conn.close()

        return jsonify({"message": "Product registered successfully!"}), 200
    except sqlite3.IntegrityError:
        return jsonify({"message": "Product ID already exists!"}), 409

@app.route('/upload-qr', methods=['POST'])
def upload_qr():
    if 'qr_image' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['qr_image']
    img_bytes = file.read()

    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    qr_codes = decode(img)
    if not qr_codes:
        return jsonify({'status': 'invalid', 'message': 'No QR code detected'}), 404

    # Read only the first QR
    product_id = qr_codes[0].data.decode("utf-8")

    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, manufacturer FROM products WHERE product_id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if product:
        return jsonify({
            "status": "valid",
            "name": product[0],
            "manufacturer": product[1]
        })
    else:
        return jsonify({"status": "invalid"})




@app.route('/verify-product', methods=['POST'])
def verify_product():
    data = request.get_json()
    product_id = data.get('product_id')

    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, manufacturer FROM products WHERE product_id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if product:
        return jsonify({
            "status": "valid",
            "name": product[0],
            "manufacturer": product[1]
        })
    else:
        return jsonify({ "status": "invalid" })


@app.route('/report-counterfeit', methods=['POST'])
def report_counterfeit():
    qr_data = request.json['qr_code_data']
    result = db.products.update_one({"qr_code_data": qr_data}, {"$set": {"is_valid": False}})
    if result.modified_count > 0:
        return jsonify({"message": "Product marked as counterfeit"}), 200
    return jsonify({"message": "QR code not found"}), 404

@app.route('/product/<product_id>', methods=['GET'])
def get_product(product_id):
    product = db.products.find_one({"product_id": product_id})
    if product:
        product['_id'] = str(product['_id'])
        return jsonify(product), 200
    return jsonify({"message": "Product not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)

CREDENTIAL_FILE = 'credentials.json'

# Ensure the credential file exists
if not os.path.exists(CREDENTIAL_FILE):
    with open(CREDENTIAL_FILE, 'w') as f:
        json.dump({'users': [], 'manufacturers': []}, f)

def load_credentials():
    with open(CREDENTIAL_FILE, 'r') as f:
        return json.load(f)

def save_credentials(data):
    with open(CREDENTIAL_FILE, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.form
    role = data.get('role')
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    creds = load_credentials()
    user_type = 'users' if role == 'user' else 'manufacturers'

    if any(u['email'] == email for u in creds[user_type]):
        return jsonify({'status': 'error', 'message': 'Email already exists'}), 409

    creds[user_type].append({'name': name, 'email': email, 'password': password})
    save_credentials(creds)
    return jsonify({'status': 'success', 'message': 'Signup successful'}), 200

@app.route('/login', methods=['POST'])
def login():
    data = request.form
    role = data.get('role')
    email = data.get('email')
    password = data.get('password')

    creds = load_credentials()
    user_type = 'users' if role == 'user' else 'manufacturers'

    for user in creds[user_type]:
        if user['email'] == email and user['password'] == password:
            return jsonify({'status': 'success', 'name': user['name']}), 200

    return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401
