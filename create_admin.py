import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("database.db")
c = conn.cursor()

# Check if admin already exists
c.execute("SELECT * FROM users WHERE email=?", ("admin@gmail.com",))
existing = c.fetchone()

if existing:
    print("Admin already exists!")
else:
    hashed_password = generate_password_hash("admin123")

    c.execute("""
        INSERT INTO users (name, email, password, role)
        VALUES (?, ?, ?, ?)
    """, ("Admin", "admin@gmail.com", hashed_password, "admin"))

    conn.commit()
    print("Admin created successfully!")

conn.close()
