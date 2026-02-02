from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import boto3  # AWS SDK

# --- AWS CONFIGURATION ---
# AWS Elastic Beanstalk looks for the 'application' variable
application = app = Flask(__name__)
application.secret_key = "aws_secret_key_change_me"

# --- AWS SNS CONFIGURATION ---
# REPLACE THIS ARN with yours from the AWS Console!
SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:123456789012:MyFruitStoreOrders'
sns_client = boto3.client('sns', region_name='us-east-1')

# --- FILE CONFIGURATION ---
DATA_FILE = "users.json"
PRODUCTS_FILE = "products.json"

# ADMIN CREDENTIALS
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("admin123") 

# --- DEFAULT PRODUCTS ---
DEFAULT_PRODUCTS = [
    {"id": 1, "name": "Banana", "price": 40, "mrp": 40, "image": "https://images.unsplash.com/photo-1603833665858-e61d17a86224?w=400"},
    {"id": 2, "name": "Papaya", "price": 60, "mrp": 80, "image": "https://images.unsplash.com/photo-1617112848923-cc9eb10303be?w=400"},
    {"id": 3, "name": "Guava", "price": 60, "mrp": 60, "image": "https://upload.wikimedia.org/wikipedia/commons/0/02/Guava_ID.jpg"},
    {"id": 4, "name": "Strawberry", "price": 150, "mrp": 150, "image": "https://images.unsplash.com/photo-1464965911861-746a04b4bca6?w=400"},
    {"id": 5, "name": "Grapes", "price": 120, "mrp": 120, "image": "https://images.unsplash.com/photo-1537640538965-1756526e0c55?w=400"},
    {"id": 6, "name": "Pineapple", "price": 90, "mrp": 90, "image": "https://images.unsplash.com/photo-1550258987-190a2d41a8ba?w=400"},
    {"id": 7, "name": "Orange", "price": 70, "mrp": 70, "image": "https://images.unsplash.com/photo-1547514701-42782101795e?w=400"},
    {"id": 10, "name": "Watermelon", "price": 40, "mrp": 60, "image": "https://images.unsplash.com/photo-1587049352846-4a222e784d38?w=400"},
    {"id": 12, "name": "Tomato", "price": 50, "mrp": 50, "image": "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=400"},
    {"id": 13, "name": "Onion", "price": 30, "mrp": 30, "image": "https://images.unsplash.com/photo-1618512496248-a07fe83aa829?w=400"},
    {"id": 22, "name": "Potato", "price": 35, "mrp": 35, "image": "https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=400"}
]

# --- HELPER FUNCTIONS ---

def load_json(filename, default_data):
    if not os.path.exists(filename):
        try:
            with open(filename, "w") as f: json.dump(default_data, f)
        except IOError:
            return default_data
        return default_data
    with open(filename, "r") as f: return json.load(f)

def save_json(filename, data):
    try:
        with open(filename, "w") as f: json.dump(data, f)
    except IOError:
        pass # AWS filesystems are often read-only

def get_all_products():
    return load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)

# --- USER ROUTES ---

@application.route("/")
def home():
    query = request.args.get('q')
    products = get_all_products()
    if query:
        products = [p for p in products if query.lower() in p['name'].lower()]
    return render_template("home.html", products=products, query=query)

@application.route("/cart")
def cart():
    cart_data = session.get('cart', {})
    items = []
    total = 0
    all_products = {p['id']: p for p in get_all_products()}
    for pid_str, qty in cart_data.items():
        p = all_products.get(int(pid_str))
        if p:
            subtotal = p['price'] * float(qty)
            items.append({**p, 'qty': float(qty), 'subtotal': subtotal})
            total += subtotal
    return render_template('cart.html', items=items, total=total)

@application.route('/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json() if request.is_json else request.form
    pid = str(data.get('product_id'))
    qty = float(data.get('qty', 1))
    cart_data = session.get('cart', {})
    cart_data[pid] = float(cart_data.get(pid, 0)) + qty
    session['cart'] = cart_data
    return jsonify({'success': True}) if request.is_json else redirect(url_for('cart'))

@application.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'GET':
        cart_data = session.get('cart', {})
        total = 0
        all_products = {p['id']: p for p in get_all_products()}
        items = []
        for pid, qty in cart_data.items():
            p = all_products.get(int(pid))
            if p:
                items.append(p)
                total += p['price'] * float(qty)
        
        address_data = {}
        if 'user' in session:
            users = load_json(DATA_FILE, {})
            address_data = users.get(session['user'], {}).get('address', {})
        return render_template('checkout.html', items=items, total=total, address_data=address_data)

    name = request.form.get('name')
    address = request.form.get('address')
    payment = request.form.get('payment')
    total_val = request.form.get('total_amt', '0.00')

    # --- AWS SNS ALERT ---
    try:
        sns_message = f"NEW ORDER RECEIVED!\n\nCustomer: {name}\nTotal: ₹{total_val}\nAddress: {address}\nPayment: {payment}"
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=sns_message,
            Subject="🍎 New Fruit Store Order"
        )
    except Exception as e:
        print(f"SNS Notification Failed: {e}")

    session['cart'] = {}
    order = {'name': name, 'address_full': address, 'payment': payment}
    return render_template('order_confirmation.html', order=order)



@application.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_json(DATA_FILE, {})
        email = request.form.get('email')
        pwd = request.form.get('password')
        user = users.get(email)
        if user and check_password_hash(user['password'], pwd):
            session['user'] = email
            return redirect(url_for('home'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@application.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        users = load_json(DATA_FILE, {})
        email = request.form.get('email')
        pwd = request.form.get('password')
        if email in users: return render_template('signup.html', error='User exists')
        users[email] = {'password': generate_password_hash(pwd)}
        save_json(DATA_FILE, users)
        session['user'] = email
        return redirect(url_for('home'))
    return render_template('signup.html')

@application.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- ADMIN ROUTES ---

@application.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, request.form.get('password')):
            session['is_admin'] = True
            return redirect(url_for('add_product'))
    return render_template('admin_login.html')

@application.route('/admin/add', methods=['GET', 'POST'])
def add_product():
    if not session.get('is_admin'): return redirect(url_for('admin_login'))
    if request.method == 'POST':
        products = get_all_products()
        new_product = {
            "id": max([p['id'] for p in products]) + 1 if products else 1,
            "name": request.form.get('name'),
            "price": float(request.form.get('price')),
            "mrp": float(request.form.get('mrp') or request.form.get('price')),
            "image": request.form.get('image')
        }
        products.append(new_product)
        save_json(PRODUCTS_FILE, products)
        return render_template('add_product.html', success=f"Added {new_product['name']}!")
    return render_template('add_product.html')

if __name__ == '__main__':
    application.run(debug=True)