from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import boto3
from boto3.dynamodb.conditions import Key, Attr
import uuid
import os
import re
from datetime import datetime
from decimal import Decimal

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'freshbasket_aws_secure_key_2026')

# AWS Clients Setup
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
sns_client = boto3.client('sns', region_name=AWS_REGION)

# DynamoDB Table Names
USERS_TABLE = dynamodb.Table('FreshBasket_Users')
PRODUCTS_TABLE = dynamodb.Table('FreshBasket_Products')
ORDERS_TABLE = dynamodb.Table('FreshBasket_Orders')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

# ADMIN CREDENTIALS
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123'))

# Helper to handle DynamoDB Decimal types for JSON/Frontend
def decimal_to_float(obj):
    if isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

# --- PRODUCT LOGIC ---
def get_all_products():
    response = PRODUCTS_TABLE.scan()
    return decimal_to_float(response.get('Items', []))

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
            sub = float(p['price']) * float(qty)
            items.append({**p, 'qty': float(qty), 'subtotal': sub})
            total += sub
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    pid = str(request.form.get('product_id', ''))
    qty = float(request.form.get('qty', 1))
    
    try:
        response = PRODUCTS_TABLE.get_item(Key={'id': pid})
        product = response.get('Item')
        if not product:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': 'Error fetching product'}), 500
    
    cart_data = session.get('cart', {})
    cart_data[pid] = float(cart_data.get(pid, 0)) + qty
    session['cart'] = cart_data
    session.modified = True
    
    product_name = decimal_to_float(product.get('name', 'Product'))
    return jsonify({
        'success': True,
        'message': f'Added {product_name} to cart',
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
    
    # Fetch User from DynamoDB
    user_res = USERS_TABLE.get_item(Key={'email': user_email})
    user_data = user_res.get('Item', {'email': user_email, 'address': {}})

    cart_data = session.get('cart', {})
    all_p = {str(p['id']): p for p in get_all_products()}
    items_to_save, total_val = [], 0
    
    for pid, qty in cart_data.items():
        if pid in all_p:
            p = all_p[pid]
            sub = float(p['price']) * float(qty)
            items_to_save.append({'name': p['name'], 'qty': Decimal(str(qty)), 'subtotal': Decimal(str(sub))})
            total_val += sub

    if request.method == 'POST':
        addr = {
            'name': request.form.get('name'),
            'phone': request.form.get('phone'),
            'address': request.form.get('address'),
            'pincode': request.form.get('pincode'),
            'taluk': request.form.get('taluk')
        }
        
        # Update User Address in DynamoDB
        USERS_TABLE.update_item(
            Key={'email': user_email},
            UpdateExpression="set address = :a",
            ExpressionAttributeValues={':a': addr}
        )

        order_id = str(uuid.uuid4())[:8]
        order_item = {
            'order_id': order_id,
            'user_email': user_email,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'items': items_to_save,
            'total': Decimal(str(total_val)),
            'address': addr,
            'payment': request.form.get('payment', 'Cash on Delivery')
        }
        
        ORDERS_TABLE.put_item(Item=order_item)

        # Send SNS notification
        if SNS_TOPIC_ARN:
            try:
                sns_client.publish(
                    TopicArn=SNS_TOPIC_ARN, 
                    Message=f"New Order {order_id} placed by {addr['name']} for ₹{total_val}", 
                    Subject="FreshBasket Order Confirmed"
                )
            except Exception as e:
                print(f"SNS Error: {e}")

        session.pop('cart', None)
        return render_template('order_confirmation.html', order=addr, payment_method=order_item['payment'], total=total_val, order_id=order_id)

    saved_addr = decimal_to_float(user_data.get('address', {}))
    return render_template('checkout.html', address_data=saved_addr, items=decimal_to_float(items_to_save), total=total_val)

@app.route('/history')
def history():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        response = ORDERS_TABLE.scan(
            FilterExpression=Attr('user_email').eq(session['user'])
        )
        user_orders = decimal_to_float(response.get('Items', []))
        user_orders.sort(key=lambda x: x.get('date', ''), reverse=True)
        return render_template('history.html', orders=user_orders)
    except Exception as e:
        print(f"Error loading order history: {e}")
        return render_template('history.html', orders=[])

# --- ADMIN ROUTES ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        if user == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, pwd):
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error="Invalid admin credentials")
    return render_template('admin_login.html')

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
        new_id = str(uuid.uuid4())[:8]
        item = {
            "id": new_id,
            "name": request.form.get('name'),
            "price": Decimal(request.form.get('price')),
            "mrp": Decimal(request.form.get('mrp') or request.form.get('price')),
            "image": request.form.get('image')
        }
        PRODUCTS_TABLE.put_item(Item=item)
        return redirect(url_for('admin_dashboard'))

    return render_template('add_product.html')

@app.route('/admin/edit/<pid>', methods=['GET', 'POST'])
def edit_product(pid):
    if not session.get('is_admin'): 
        return redirect(url_for('admin_login'))
    
    response = PRODUCTS_TABLE.get_item(Key={'id': pid})
    product = decimal_to_float(response.get('Item'))
    
    if request.method == 'POST' and product:
        PRODUCTS_TABLE.update_item(
            Key={'id': pid},
            UpdateExpression="set #n = :name, price = :price, mrp = :mrp, image = :image",
            ExpressionAttributeNames={'#n': 'name'},
            ExpressionAttributeValues={
                ':name': request.form.get('name'),
                ':price': Decimal(request.form.get('price')),
                ':mrp': Decimal(request.form.get('mrp') or request.form.get('price')),
                ':image': request.form.get('image')
            }
        )
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_product.html', product=product)

@app.route('/admin/delete/<pid>', methods=['POST'])
def delete_product(pid):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    try:
        PRODUCTS_TABLE.delete_item(Key={'id': pid})
    except Exception as e:
        print(f"Error deleting product: {e}")
    
    return redirect(url_for('admin_dashboard'))

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        response = USERS_TABLE.get_item(Key={'email': email})
        user = response.get('Item')
        
        if user and check_password_hash(user['password'], pwd):
            session['user'] = email
            return redirect(url_for('home'))
        
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        pwd = request.form.get('password')

        email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
        if not re.match(email_pattern, email):
            return render_template('signup.html', error="Enter a valid email address")

        response = USERS_TABLE.get_item(Key={'email': email})
        if response.get('Item'):
            return render_template('signup.html', error="Email already registered")

        USERS_TABLE.put_item(Item={
            'email': email,
            'password': generate_password_hash(pwd),
            'address': {}
        })
        session['user'] = email
        return redirect(url_for('home'))
    return render_template('signup.html')
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)