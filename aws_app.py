from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import boto3
import uuid
from datetime import datetime
import json
from decimal import Decimal

from app import PRODUCTS_FILE, save_json

# --- AWS CONFIGURATION ---
application = app = Flask(__name__)
application.secret_key = "aws_secret_key_change_me"

REGION = 'us-east-1'
SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:123456789012:MyFruitStoreOrders'

# Initialize AWS Clients
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)

# DynamoDB Tables
product_table = dynamodb.Table('Products')
user_table = dynamodb.Table('Users')
order_table = dynamodb.Table('Orders')

# --- HELPER FUNCTIONS ---

def decimal_to_float(obj):
    """Helper to convert DynamoDB Decimals to Python floats for JSON/Templates"""
    if isinstance(obj, list): return [decimal_to_float(i) for i in obj]
    elif isinstance(obj, dict): return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal): return float(obj)
    return obj

def get_all_products():
    response = product_table.scan()
    return decimal_to_float(response.get('Items', []))

# --- USER ROUTES ---

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
            subtotal = p['price'] * float(qty)
            items.append({**p, 'qty': float(qty), 'subtotal': subtotal})
            total += subtotal
    return render_template('cart.html', items=items, total=total)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user' not in session: return redirect(url_for('login'))
    user_email = session['user']
    
    # Calculate cart data for both GET and POST
    cart_data = session.get('cart', {})
    all_p = {str(p['id']): p for p in get_all_products()}
    items_to_save, total_val = [], 0
    for pid, qty in cart_data.items():
        if pid in all_p:
            p = all_p[pid]
            sub = p['price'] * float(qty)
            items_to_save.append({'name': p['name'], 'qty': float(qty), 'subtotal': sub})
            total_val += sub

    if request.method == 'GET':
        # Fetch saved address from DynamoDB Users table
        user_res = user_table.get_item(Key={'email': user_email})
        address_data = user_res.get('Item', {}).get('address', {})
        return render_template('checkout.html', items=items_to_save, total=total_val, address_data=address_data)

    # POST Logic: Process Order
    name = request.form.get('name')
    address = request.form.get('address')
    phone = request.form.get('phone')
    payment = request.form.get('payment', 'Cash on Delivery')

    # 1. Update User's saved address
    user_table.update_item(
        Key={'email': user_email},
        UpdateExpression="set #addr = :a",
        ExpressionAttributeNames={'#addr': 'address'},
        ExpressionAttributeValues={':a': {'name': name, 'address': address, 'phone': phone}}
    )

    # 2. Save Order to History
    order_id = str(uuid.uuid4())[:8]
    order_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    order_item = {
        'order_id': order_id,
        'user_email': user_email,
        'date': order_date,
        'items': items_to_save,
        'total': Decimal(str(total_val)),
        'address': address,
        'payment': payment
    }
    order_table.put_item(Item=order_item)

    # 3. AWS SNS Detailed Alert
    try:
        sns_message = (f"🍎 NEW ORDER: {order_id}\n\n"
                       f"Customer: {name}\n"
                       f"Phone: {phone}\n"
                       f"Total: ₹{total_val}\n"
                       f"Address: {address}\n"
                       f"Payment: {payment}")
        sns_client.publish(TopicArn=SNS_TOPIC_ARN, Message=sns_message, Subject="New Fruit Store Order")
    except Exception as e: print(f"SNS Failed: {e}")

    session['cart'] = {}
    return render_template('order_confirmation.html', order=order_item, payment_method=payment)

@app.route('/history')
def history():
    if 'user' not in session: return redirect(url_for('login'))
    user_email = session['user']
    
    # Scan orders for this user
    response = order_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('user_email').eq(user_email)
    )
    user_orders = decimal_to_float(response.get('Items', []))
    user_orders.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('history.html', orders=user_orders)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        response = user_table.get_item(Key={'email': email})
        user = response.get('Item')
        if user and check_password_hash(user['password'], pwd):
            session['user'] = email
            return redirect(url_for('home'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        # Check if user exists
        if 'Item' in user_table.get_item(Key={'email': email}):
            return render_template('signup.html', error='User already exists')
        
        user_table.put_item(Item={
            'email': email,
            'password': generate_password_hash(pwd),
            'address': {}
        })
        session['user'] = email
        return redirect(url_for('home'))
    return render_template('signup.html')
# --- ADMIN DASHBOARD (To view all products) ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('is_admin'): 
        return redirect(url_for('admin_login'))
    products = get_all_products()
    return render_template('admin_dashboard.html', products=products)

# --- ADD PRODUCT ROUTE ---
@app.route('/admin/add', methods=['GET', 'POST'])
def add_product():
    if not session.get('is_admin'): 
        return redirect(url_for('admin_login'))
        
    if request.method == 'POST':
        products = get_all_products()
        
        # 1. Create the new product object
        new_product = {
            "id": max([p['id'] for p in products]) + 1 if products else 1,
            "name": request.form.get('name'),
            "price": float(request.form.get('price')),
            "mrp": float(request.form.get('mrp') or request.form.get('price')),
            "image": request.form.get('image')
        }
        
        # 2. Save it
        products.append(new_product)
        save_json(PRODUCTS_FILE, products)
        
        # 3. FIX: Redirect to the DASHBOARD so you can see the new item
        return redirect(url_for('admin_dashboard'))
        
    return render_template('add_product.html')
if __name__ == '__main__':
    app.run(debug=True)