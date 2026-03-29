import sqlite3
from flask import Flask, request, render_template, redirect, session, flash
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"


# =========================
# DB HELPER
# =========================
def get_db():
    return sqlite3.connect('database.db')


# =========================
# AUTH DECORATORS
# =========================
def login_required(func):
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def admin_required(func):
    def wrapper(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            return "Access Denied" 
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# =========================
# REGISTER
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form

        password = data['password']
        confirm_password = data['confirm_password']

        # ✅ Confirm password check
        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect('/register')

        hashed_password = generate_password_hash(password)

        conn = get_db()
        c = conn.cursor()

        try:
            c.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, ?)
            """, (data['name'], data['email'], hashed_password, "user"))

            conn.commit()
            flash("Account created! Please login.", "success")

        except:
            flash("Email already exists", "danger")

        conn.close()
        return redirect('/register')

    return render_template('register.html')


# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT id, name, password, role FROM users WHERE email=?", (data['email'],))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], data['password']):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['role'] = user[3]
            return redirect('/dashboard')

        flash("Invalid email or password", "danger")
        return redirect('/login')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# =========================
# AUTO EXPIRE
# =========================
def auto_expire():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE subscriptions
        SET status='expired'
        WHERE end_date < date('now')
    """)

    conn.commit()
    conn.close()


# =========================
# DASHBOARD
# =========================
@app.route('/')
def home():
    return redirect('/dashboard')


@app.route('/dashboard')
@login_required
def dashboard():
    if session.get('role') == 'admin':
        return redirect('/admin')

    auto_expire()

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT s.id, p.name, s.start_date, s.end_date, s.status
        FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id
        WHERE s.user_id = ?
    """, (session['user_id'],))

    subs = c.fetchall()
    conn.close()

    updated_subs = []
    for sub in subs:
        end_date = datetime.strptime(sub[3], "%Y-%m-%d")
        days_left = (end_date - datetime.now()).days
        updated_subs.append(sub + (days_left,))

    return render_template('dashboard.html', subscriptions=updated_subs)


# =========================
# PLANS
# =========================
@app.route('/plans')
@login_required
def plans():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM plans")
    plans = c.fetchall()

    conn.close()

    return render_template('plans.html', plans=plans)


# =========================
# SUBSCRIBE
# =========================
@app.route('/subscribe/<int:plan_id>')
@login_required
def subscribe(plan_id):

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT billing_cycle FROM plans WHERE id=?", (plan_id,))
    cycle = c.fetchone()[0]

    start = datetime.now()

    if cycle.lower() == "yearly":
        end = start + timedelta(days=365)
    else:
        end = start + timedelta(days=30)

    # expire old
    c.execute("""
        UPDATE subscriptions
        SET status='expired'
        WHERE user_id=? AND status='active'
    """, (session['user_id'],))

    # new sub
    c.execute("""
        INSERT INTO subscriptions (user_id, plan_id, start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session['user_id'],
        plan_id,
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        "active"
    ))

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# =========================
# CANCEL
# =========================
@app.route('/cancel/<int:sub_id>')
@login_required
def cancel(sub_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE subscriptions
        SET status='canceled'
        WHERE id=? AND user_id=?
    """, (sub_id, session['user_id']))

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# =========================
# ADMIN
# =========================
@app.route('/admin')
@admin_required
def admin():
    auto_expire()

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT s.id, u.name, p.name, s.status, s.end_date
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        JOIN plans p ON s.plan_id = p.id
    """)
    subs = c.fetchall()

    c.execute("SELECT * FROM plans")
    plans = c.fetchall()

    conn.close()

    return render_template('admin.html', subscriptions=subs, plans=plans)


@app.route('/admin/create_plan', methods=['POST'])
@admin_required
def create_plan():
    data = request.form

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO plans (name, price, billing_cycle)
        VALUES (?, ?, ?)
    """, (data['name'], data['price'], data['billing_cycle']))

    conn.commit()
    conn.close()

    return redirect('/admin')


@app.route('/admin/delete_plan/<int:plan_id>')
@admin_required
def delete_plan(plan_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    conn.commit()
    conn.close()

    return redirect('/admin')


# =========================
# RUN
# =========================
if __name__ == '__main__':
    app.run(debug=True, port=5001)