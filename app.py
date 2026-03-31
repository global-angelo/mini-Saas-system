import sqlite3
from flask import Flask, request, render_template, redirect, session, flash
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "supersecretkey"


# =========================
# DB HELPER
# =========================
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# AUTH DECORATORS
# =========================
def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            flash("Access denied", "danger")
            return redirect("/login")
        return func(*args, **kwargs)
    return wrapper


# =========================
# AUTO EXPIRE
# =========================
def auto_expire():
    conn = get_db()
    conn.execute("""
        UPDATE subscriptions SET status='expired'
        WHERE end_date < date('now') AND status='active'
    """)
    conn.commit()
    conn.close()


# =========================
# AUTH ROUTES
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form

        if data['password'] != data['confirm_password']:
            flash("Passwords do not match", "danger")
            return redirect('/register')

        hashed = generate_password_hash(data['password'])
        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                (data['name'], data['email'], hashed, "user")
            )
            conn.commit()
            flash("Account created! Please login.", "success")
        except Exception:
            flash("Email already exists", "danger")

        conn.close()
        return redirect('/register')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (data['email'],)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], data['password']):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['role'] = user['role']
            return redirect('/dashboard')

        flash("Invalid email or password", "danger")
        return redirect('/login')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# =========================
# USER ROUTES
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

    subs = conn.execute("""
        SELECT s.id, p.name as plan_name, s.start_date, s.end_date, s.status,
               p.price, p.billing_cycle
        FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id
        WHERE s.user_id = ?
        ORDER BY s.id DESC
    """, (session['user_id'],)).fetchall()

    # Get active subscription info
    active_sub = conn.execute("""
        SELECT s.*, p.name as plan_name, p.price, p.billing_cycle
        FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id
        WHERE s.user_id = ? AND s.status = 'active'
        ORDER BY s.id DESC LIMIT 1
    """, (session['user_id'],)).fetchone()

    # Count accessible courses
    course_count = 0
    if active_sub:
        active_price = conn.execute("SELECT price FROM plans WHERE id=?", (active_sub['plan_id'],)).fetchone()
        if active_price:
            course_count = conn.execute(
                "SELECT COUNT(*) FROM courses c JOIN plans p ON c.plan_id=p.id WHERE p.price<=?",
                (active_price['price'],)
            ).fetchone()[0]

    # Check for pending cancellation
    pending_cancel = None
    if active_sub:
        pending_cancel = conn.execute("""
            SELECT * FROM cancellation_requests
            WHERE subscription_id=? AND status='pending'
        """, (active_sub['id'],)).fetchone()

    conn.close()
    return render_template('dashboard.html',
                           subscriptions=subs,
                           active_sub=active_sub,
                           course_count=course_count,
                           pending_cancel=pending_cancel)


@app.route('/plans')
@login_required
def plans():
    conn = get_db()
    all_plans = conn.execute("SELECT * FROM plans WHERE status='active' ORDER BY price").fetchall()

    active_sub = conn.execute("""
        SELECT s.plan_id, p.name as plan_name FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id
        WHERE s.user_id = ? AND s.status = 'active'
        ORDER BY s.id DESC LIMIT 1
    """, (session['user_id'],)).fetchone()

    conn.close()
    active_plan_id = active_sub['plan_id'] if active_sub else None
    return render_template('plans.html', plans=all_plans, active_plan_id=active_plan_id)


@app.route('/subscribe/<int:plan_id>')
@login_required
def subscribe(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM plans WHERE id=? AND status='active'", (plan_id,)).fetchone()

    if not plan:
        flash("Plan not available", "danger")
        conn.close()
        return redirect('/plans')

    start = datetime.now()
    cycle = plan['billing_cycle'].lower()

    if cycle == 'yearly':
        end = start + timedelta(days=365)
    elif cycle == 'quarterly':
        end = start + timedelta(days=90)
    else:
        end = start + timedelta(days=30)

    # Expire old active subscriptions
    conn.execute("""
        UPDATE subscriptions SET status='expired'
        WHERE user_id=? AND status='active'
    """, (session['user_id'],))

    conn.execute("""
        INSERT INTO subscriptions (user_id, plan_id, start_date, end_date, status)
        VALUES (?, ?, ?, ?, 'active')
    """, (session['user_id'], plan_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))

    conn.commit()
    conn.close()

    flash(f"Successfully subscribed to {plan['name']}!", "success")
    return redirect('/dashboard')


@app.route('/my-courses')
@login_required
def my_courses():
    conn = get_db()

    active_sub = conn.execute("""
        SELECT s.*, p.name as plan_name, p.price
        FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id
        WHERE s.user_id = ? AND s.status = 'active'
        ORDER BY s.id DESC LIMIT 1
    """, (session['user_id'],)).fetchone()

    courses = []
    if active_sub:
        courses = conn.execute("""
            SELECT c.*, p.name as plan_name FROM courses c
            JOIN plans p ON c.plan_id = p.id
            WHERE p.price <= ?
            ORDER BY p.price, c.title
        """, (active_sub['price'],)).fetchall()

    conn.close()
    return render_template('my_courses.html', courses=courses, active_sub=active_sub)


@app.route('/request-cancellation/<int:sub_id>', methods=['POST'])
@login_required
def request_cancellation(sub_id):
    conn = get_db()

    sub = conn.execute("""
        SELECT * FROM subscriptions WHERE id=? AND user_id=? AND status='active'
    """, (sub_id, session['user_id'])).fetchone()

    if not sub:
        flash("Invalid subscription", "danger")
        conn.close()
        return redirect('/dashboard')

    existing = conn.execute("""
        SELECT * FROM cancellation_requests WHERE subscription_id=? AND status='pending'
    """, (sub_id,)).fetchone()

    if existing:
        flash("You already have a pending cancellation request", "warning")
        conn.close()
        return redirect('/cancellation-status')

    reason = request.form.get('reason', '')
    conn.execute("""
        INSERT INTO cancellation_requests (subscription_id, user_id, reason, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
    """, (sub_id, session['user_id'], reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()

    flash("Cancellation request submitted", "success")
    return redirect('/cancellation-status')


@app.route('/cancellation-status')
@login_required
def cancellation_status():
    conn = get_db()

    requests = conn.execute("""
        SELECT cr.*, p.name as plan_name, s.start_date, s.end_date
        FROM cancellation_requests cr
        JOIN subscriptions s ON cr.subscription_id = s.id
        JOIN plans p ON s.plan_id = p.id
        WHERE cr.user_id = ?
        ORDER BY cr.created_at DESC
    """, (session['user_id'],)).fetchall()

    conn.close()
    return render_template('cancellation_status.html', requests=requests)


# =========================
# ADMIN ROUTES
# =========================
@app.route('/admin')
@admin_required
def admin():
    auto_expire()
    conn = get_db()

    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
    total_plans = conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
    active_subs = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status='active'").fetchone()[0]
    pending_cancellations = conn.execute("SELECT COUNT(*) FROM cancellation_requests WHERE status='pending'").fetchone()[0]
    total_courses = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]

    revenue = conn.execute("""
        SELECT COALESCE(SUM(p.price), 0) FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id WHERE s.status='active'
    """).fetchone()[0]

    recent_subs = conn.execute("""
        SELECT s.id, u.name as user_name, p.name as plan_name, s.status, s.start_date, s.end_date
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        JOIN plans p ON s.plan_id = p.id
        ORDER BY s.id DESC LIMIT 10
    """).fetchall()

    plans = conn.execute("SELECT * FROM plans ORDER BY price").fetchall()
    conn.close()

    return render_template('admin.html',
                           total_users=total_users,
                           total_plans=total_plans,
                           active_subs=active_subs,
                           pending_cancellations=pending_cancellations,
                           total_courses=total_courses,
                           revenue=revenue,
                           recent_subs=recent_subs,
                           plans=plans)


@app.route('/admin/create_plan', methods=['POST'])
@admin_required
def create_plan():
    data = request.form
    conn = get_db()
    conn.execute("""
        INSERT INTO plans (name, description, price, billing_cycle, status)
        VALUES (?, ?, ?, ?, 'active')
    """, (data['name'], data.get('description', ''), data['price'], data['billing_cycle']))
    conn.commit()
    conn.close()
    flash("Plan created successfully", "success")
    return redirect('/admin')


@app.route('/admin/edit_plan/<int:plan_id>', methods=['GET', 'POST'])
@admin_required
def edit_plan(plan_id):
    conn = get_db()

    if request.method == 'POST':
        data = request.form
        conn.execute("""
            UPDATE plans SET name=?, description=?, price=?, billing_cycle=? WHERE id=?
        """, (data['name'], data.get('description', ''), data['price'], data['billing_cycle'], plan_id))
        conn.commit()
        conn.close()
        flash("Plan updated successfully", "success")
        return redirect('/admin')

    plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    conn.close()

    if not plan:
        flash("Plan not found", "danger")
        return redirect('/admin')

    return render_template('admin_edit_plan.html', plan=plan)


@app.route('/admin/toggle_plan/<int:plan_id>')
@admin_required
def toggle_plan(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT status FROM plans WHERE id=?", (plan_id,)).fetchone()

    if plan:
        new_status = 'inactive' if plan['status'] == 'active' else 'active'
        conn.execute("UPDATE plans SET status=? WHERE id=?", (new_status, plan_id))
        conn.commit()
        flash(f"Plan {'activated' if new_status == 'active' else 'deactivated'}", "success")

    conn.close()
    return redirect('/admin')


@app.route('/admin/delete_plan/<int:plan_id>')
@admin_required
def delete_plan(plan_id):
    conn = get_db()
    conn.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    conn.commit()
    conn.close()
    flash("Plan deleted", "success")
    return redirect('/admin')


@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute("""
        SELECT u.*,
               (SELECT COUNT(*) FROM subscriptions WHERE user_id=u.id AND status='active') as active_subs,
               (SELECT p.name FROM subscriptions s JOIN plans p ON s.plan_id=p.id
                WHERE s.user_id=u.id AND s.status='active' ORDER BY s.id DESC LIMIT 1) as current_plan
        FROM users u WHERE u.role='user'
        ORDER BY u.id DESC
    """).fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)


@app.route('/admin/courses')
@admin_required
def admin_courses():
    conn = get_db()
    courses = conn.execute("""
        SELECT c.*, p.name as plan_name
        FROM courses c
        JOIN plans p ON c.plan_id = p.id
        ORDER BY p.price, c.title
    """).fetchall()
    plans = conn.execute("SELECT * FROM plans WHERE status='active' ORDER BY price").fetchall()
    conn.close()
    return render_template('admin_courses.html', courses=courses, plans=plans)


@app.route('/admin/create_course', methods=['POST'])
@admin_required
def create_course():
    data = request.form
    conn = get_db()
    conn.execute(
        "INSERT INTO courses (title, description, plan_id) VALUES (?, ?, ?)",
        (data['title'], data.get('description', ''), data['plan_id'])
    )
    conn.commit()
    conn.close()
    flash("Course added successfully", "success")
    return redirect('/admin/courses')


@app.route('/admin/edit_course/<int:course_id>', methods=['POST'])
@admin_required
def edit_course(course_id):
    data = request.form
    conn = get_db()
    conn.execute(
        "UPDATE courses SET title=?, description=?, plan_id=? WHERE id=?",
        (data['title'], data.get('description', ''), data['plan_id'], course_id)
    )
    conn.commit()
    conn.close()
    flash("Course updated", "success")
    return redirect('/admin/courses')


@app.route('/admin/delete_course/<int:course_id>')
@admin_required
def delete_course(course_id):
    conn = get_db()
    conn.execute("DELETE FROM courses WHERE id=?", (course_id,))
    conn.commit()
    conn.close()
    flash("Course deleted", "success")
    return redirect('/admin/courses')


@app.route('/admin/cancellations')
@admin_required
def admin_cancellations():
    conn = get_db()
    requests = conn.execute("""
        SELECT cr.*, u.name as user_name, u.email, p.name as plan_name,
               s.start_date, s.end_date
        FROM cancellation_requests cr
        JOIN users u ON cr.user_id = u.id
        JOIN subscriptions s ON cr.subscription_id = s.id
        JOIN plans p ON s.plan_id = p.id
        ORDER BY (cr.status = 'pending') DESC, cr.created_at DESC
    """).fetchall()
    conn.close()
    return render_template('admin_cancellations.html', requests=requests)


@app.route('/admin/process_cancellation/<int:req_id>', methods=['POST'])
@admin_required
def process_cancellation(req_id):
    action = request.form.get('action')
    conn = get_db()

    cr = conn.execute("SELECT * FROM cancellation_requests WHERE id=?", (req_id,)).fetchone()

    if cr and cr['status'] == 'pending':
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if action == 'approve':
            conn.execute("UPDATE cancellation_requests SET status='approved', processed_at=? WHERE id=?", (now, req_id))
            conn.execute("UPDATE subscriptions SET status='canceled' WHERE id=?", (cr['subscription_id'],))
            flash("Cancellation approved", "success")
        elif action == 'reject':
            conn.execute("UPDATE cancellation_requests SET status='rejected', processed_at=? WHERE id=?", (now, req_id))
            flash("Cancellation rejected", "info")

    conn.commit()
    conn.close()
    return redirect('/admin/cancellations')


@app.route('/admin/reports')
@admin_required
def admin_reports():
    conn = get_db()

    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]

    plan_stats = conn.execute("""
        SELECT p.name, p.price, p.billing_cycle, p.status,
               COUNT(CASE WHEN s.status='active' THEN 1 END) as active_count,
               COUNT(CASE WHEN s.status='expired' THEN 1 END) as expired_count,
               COUNT(CASE WHEN s.status='canceled' THEN 1 END) as canceled_count,
               COUNT(s.id) as total_subs
        FROM plans p
        LEFT JOIN subscriptions s ON p.id = s.plan_id
        GROUP BY p.id
        ORDER BY active_count DESC
    """).fetchall()

    active_subs = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status='active'").fetchone()[0]
    expired_subs = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status='expired'").fetchone()[0]
    canceled_subs = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status='canceled'").fetchone()[0]

    total_cancel_requests = conn.execute("SELECT COUNT(*) FROM cancellation_requests").fetchone()[0]
    pending_cancellations = conn.execute("SELECT COUNT(*) FROM cancellation_requests WHERE status='pending'").fetchone()[0]
    approved_cancellations = conn.execute("SELECT COUNT(*) FROM cancellation_requests WHERE status='approved'").fetchone()[0]
    rejected_cancellations = conn.execute("SELECT COUNT(*) FROM cancellation_requests WHERE status='rejected'").fetchone()[0]

    revenue = conn.execute("""
        SELECT COALESCE(SUM(p.price), 0) FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id WHERE s.status='active'
    """).fetchone()[0]

    recent_users = conn.execute("""
        SELECT name, email, created_at FROM users
        WHERE role='user' ORDER BY id DESC LIMIT 5
    """).fetchall()

    conn.close()
    return render_template('admin_reports.html',
                           total_users=total_users,
                           plan_stats=plan_stats,
                           active_subs=active_subs,
                           expired_subs=expired_subs,
                           canceled_subs=canceled_subs,
                           total_cancel_requests=total_cancel_requests,
                           pending_cancellations=pending_cancellations,
                           approved_cancellations=approved_cancellations,
                           rejected_cancellations=rejected_cancellations,
                           revenue=revenue,
                           recent_users=recent_users)


# =========================
# RUN
# =========================
if __name__ == '__main__':
    app.run(debug=True, port=5001)
