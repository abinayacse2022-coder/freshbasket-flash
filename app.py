from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import re
import uuid
from datetime import datetime

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'freshbasket_secure_key_2026')

DATA_FILE = "users.json"
PRODUCTS_FILE = "products.json"
ORDERS_FILE = "orders.json"

# ADMIN CREDENTIALS
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123'))

# --- DEFAULT PRODUCTS ---
DEFAULT_PRODUCTS = [
    {"id": 1, "name": "Banana", "price": 40, "image": "https://upload.wikimedia.org/wikipedia/commons/8/8a/Banana-Single.jpg"},
    {"id": 2, "name": "Papaya", "price": 80, "image": "/static/images/papaya.jpg"},
    {"id": 3, "name": "Guava", "price": 60, "image": "/static/images/guava.jpg"},
    {"id": 4, "name": "Strawberry", "price": 150, "image": "https://upload.wikimedia.org/wikipedia/commons/2/29/PerfectStrawberry.jpg"},
    {"id": 5, "name": "Grapes", "price": 120, "image": "/static/images/grapes.jpg"},
    {"id": 6, "name": "Pineapple", "price": 90, "image": "https://upload.wikimedia.org/wikipedia/commons/c/cb/Pineapple_and_cross_section.jpg"},
    {"id": 7, "name": "Orange", "price": 70, "image": "https://upload.wikimedia.org/wikipedia/commons/c/c4/Orange-Fruit-Pieces.jpg"},
    {"id": 8, "name": "Blueberry", "price": 200, "image": "data:image/jpeg;base64,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"},
    {"id": 9, "name": "Dragonfruit", "price": 220, "image": "/static/images/dragonfruit.jpg"},
    {"id": 10, "name": "Watermelon", "price": 60, "image": "/static/images/watermelon.jpg"},
    {"id": 11, "name": "Pomegranate", "price": 140, "image": "/static/images/pomegranate.jpg"},
    {"id": 12, "name": "Tomato", "price": 50, "image": "https://upload.wikimedia.org/wikipedia/commons/8/88/Bright_red_tomato_and_cross_section02.jpg"},
    {"id": 13, "name": "Onion", "price": 30, "image": "/static/images/onion.jpg"},
    {"id": 14, "name": "Beans", "price": 90, "image": "/static/images/beans.jpg"},
    {"id": 15, "name": "Peas", "price": 80, "image": "/static/images/peas.jpg"},
    {"id": 16, "name": "Brinjal", "price": 60, "image": "/static/images/brinjal.jpg"},
    {"id": 17, "name": "Cabbage", "price": 50, "image": "/static/images/cabbage.jpg"},
    {"id": 18, "name": "Cauliflower", "price": 70, "image": "/static/images/cauliflower.jpg"},
    {"id": 19, "name": "Capsicum", "price": 90, "image": "data:image/jpeg;base64,BASE64_STRING_HERE"},
    {"id": 20, "name": "Carrot", "price": 40, "image": "data:image/jpeg;base64,BASE64_STRING_HERE"},
    {"id": 21, "name": "Beetroot", "price": 60, "image": "data:image/jpeg;base64,BASE64_STRING_HERE"},
    {"id": 22, "name": "Potato", "price": 35, "image": "/static/images/potato.jpg"}
]

# --- HELPER FUNCTIONS ---
def load_json(filename, default_data):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump(default_data, f)
        return default_data
    with open(filename, "r") as f:
        try:
            return json.load(f)
        except:
            return default_data

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def get_all_products():
    return load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)

# --- PUBLIC ROUTES ---
@app.route("/")
def home():
    query = request.args.get('q')
    products = get_all_products()
    if query:
        products = [p for p in products if query.lower() in p['name'].lower()]
    return render_template("home.html", products=products, query=query)

@app.route("/cart")
def cart():
    cart_data = session.get('cart', {})
    items, total = [], 0
    all_products = {str(p['id']): p for p in get_all_products()}
    for pid, qty in cart_data.items():
        p = all_products.get(pid)
        if p:
            sub = p['price'] * float(qty)
            items.append({**p, 'qty': float(qty), 'subtotal': sub})
            total += sub
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    pid = str(request.form.get('product_id'))
    qty = float(request.form.get('qty', 1))
    
    all_products = {str(p['id']): p for p in get_all_products()}
    product = all_products.get(pid)
    
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    
    cart_data = session.get('cart', {})
    cart_data[pid] = float(cart_data.get(pid, 0)) + qty
    session['cart'] = cart_data
    
    return jsonify({
        'success': True,
        'message': f'Added {product["name"]} to cart',
        'cart_count': len(cart_data)
    })

@app.route('/cart/count')
def cart_count():
    cart_data = session.get('cart', {})
    count = len(cart_data)
    return jsonify({'count': count})

@app.route('/cart/update/<pid>', methods=['POST'])
def update_cart(pid):
    qty = float(request.form.get('qty', 0))
    cart_data = session.get('cart', {})
    
    if qty <= 0:
        cart_data.pop(pid, None)
    else:
        cart_data[pid] = qty
    
    session['cart'] = cart_data
    return redirect(url_for('cart'))

@app.route('/cart/remove/<pid>')
def remove_from_cart(pid):
    cart_data = session.get('cart', {})
    cart_data.pop(pid, None)
    session['cart'] = cart_data
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user_email = session['user']
    users = load_json(DATA_FILE, {})

    if user_email not in users:
        users[user_email] = {'password': '', 'address': {}}

    cart_data = session.get('cart', {})
    all_p = {str(p['id']): p for p in get_all_products()}
    items_to_save, total_val = [], 0
    
    for pid, qty in cart_data.items():
        if pid in all_p:
            p = all_p[pid]
            sub = p['price'] * float(qty)
            items_to_save.append({'name': p['name'], 'qty': float(qty), 'subtotal': sub})
            total_val += sub

    if request.method == 'POST':
        addr = {
            'name': request.form.get('name'),
            'phone': request.form.get('phone'),
            'address': request.form.get('address'),
            'pincode': request.form.get('pincode'),
            'taluk': request.form.get('taluk')
        }
        
        users[user_email]['address'] = addr
        save_json(DATA_FILE, users)

        order_id = str(uuid.uuid4())[:8]
        order_item = {
            'order_id': order_id,
            'user_email': user_email,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'items': items_to_save,
            'total': total_val,
            'address': addr,
            'payment': request.form.get('payment', 'Cash on Delivery')
        }
        
        orders = load_json(ORDERS_FILE, [])
        orders.append(order_item)
        save_json(ORDERS_FILE, orders)

        session.pop('cart', None)
        
        return render_template('order_confirmation.html',
                             order=addr,
                             payment_method=order_item['payment'],
                             total=total_val,
                             order_id=order_id)

    saved_addr = users.get(user_email, {}).get('address', {})
    return render_template('checkout.html',
                         address_data=saved_addr,
                         items=items_to_save,
                         total=total_val)

@app.route('/history')
def history():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        all_orders = load_json(ORDERS_FILE, [])
        user_orders = [o for o in all_orders if o.get('user_email') == session['user']]
        user_orders.sort(key=lambda x: x.get('date', ''), reverse=True)
        return render_template('history.html', orders=user_orders)
    except Exception as e:
        print(f"Error loading order history: {e}")
        return render_template('history.html', orders=[])

# --- ADMIN ROUTES ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html', products=get_all_products())

@app.route('/admin/add', methods=['GET', 'POST'])
def add_product():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

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
        return redirect(url_for('admin_dashboard'))

    return render_template('add_product.html')

@app.route('/admin/edit/<int:pid>', methods=['GET', 'POST'])
def edit_product(pid):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    products = get_all_products()
    product = next((p for p in products if p['id'] == pid), None)
    
    if request.method == 'POST' and product:
        product.update({
            "name": request.form.get('name'),
            "price": float(request.form.get('price')),
            "mrp": float(request.form.get('mrp') or request.form.get('price')),
            "image": request.form.get('image')
        })
        save_json(PRODUCTS_FILE, products)
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_product.html', product=product)

@app.route('/admin/delete/<int:pid>', methods=['POST'])
def delete_product(pid):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    products = get_all_products()
    products = [p for p in products if p['id'] != pid]
    save_json(PRODUCTS_FILE, products)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')

        if user == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, pwd):
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="Invalid admin credentials")

    return render_template('admin_login.html')

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_json(DATA_FILE, {})
        email, pwd = request.form.get('email'), request.form.get('password')
        if email in users and check_password_hash(users[email]['password'], pwd):
            session['user'] = email
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        users = load_json(DATA_FILE, {})
        email = (request.form.get('email') or '').strip().lower()
        pwd = request.form.get('password')

        email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
        if not re.match(email_pattern, email):
            return render_template('signup.html', error="Enter a valid email address")

        if email in users:
            return render_template('signup.html', error="Email already registered")

        users[email] = {'password': generate_password_hash(pwd), 'address': {}}
        save_json(DATA_FILE, users)
        session['user'] = email
        return redirect(url_for('home'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)