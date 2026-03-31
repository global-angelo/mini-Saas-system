import sqlite3

conn = sqlite3.connect("database.db")
c = conn.cursor()

c.execute("DROP TABLE IF EXISTS cancellation_requests")
c.execute("DROP TABLE IF EXISTS subscriptions")
c.execute("DROP TABLE IF EXISTS courses")
c.execute("DROP TABLE IF EXISTS plans")
c.execute("DROP TABLE IF EXISTS users")

c.execute('''CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now'))
)''')

c.execute('''CREATE TABLE plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    price REAL NOT NULL,
    billing_cycle TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now'))
)''')

c.execute('''CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    plan_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (plan_id) REFERENCES plans(id)
)''')

c.execute('''CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (plan_id) REFERENCES plans(id)
)''')

c.execute('''CREATE TABLE cancellation_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    reason TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    processed_at TEXT,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
)''')

# Seed some default plans
c.execute("INSERT INTO plans (name, description, price, billing_cycle) VALUES (?, ?, ?, ?)",
          ("Starter", "Perfect for beginners. Access foundational courses to start your learning journey.", 299, "Monthly"))
c.execute("INSERT INTO plans (name, description, price, billing_cycle) VALUES (?, ?, ?, ?)",
          ("Professional", "For serious learners. Unlock intermediate and advanced courses with priority support.", 799, "Monthly"))
c.execute("INSERT INTO plans (name, description, price, billing_cycle) VALUES (?, ?, ?, ?)",
          ("Enterprise", "Full access to every course. Best for teams and power learners who want it all.", 1499, "Monthly"))

# Seed some default courses
c.execute("INSERT INTO courses (title, description, plan_id) VALUES (?, ?, ?)",
          ("Introduction to Web Development", "Learn HTML, CSS, and JavaScript fundamentals from scratch.", 1))
c.execute("INSERT INTO courses (title, description, plan_id) VALUES (?, ?, ?)",
          ("Python Programming Basics", "Master Python syntax, data structures, and problem-solving techniques.", 1))
c.execute("INSERT INTO courses (title, description, plan_id) VALUES (?, ?, ?)",
          ("Database Design & SQL", "Design efficient databases and write powerful SQL queries.", 2))
c.execute("INSERT INTO courses (title, description, plan_id) VALUES (?, ?, ?)",
          ("Full-Stack Web Application", "Build complete web applications with modern frameworks and tools.", 2))
c.execute("INSERT INTO courses (title, description, plan_id) VALUES (?, ?, ?)",
          ("Cloud Computing & DevOps", "Deploy and manage applications in the cloud with CI/CD pipelines.", 3))
c.execute("INSERT INTO courses (title, description, plan_id) VALUES (?, ?, ?)",
          ("Machine Learning Foundations", "Explore ML algorithms, model training, and real-world applications.", 3))

conn.commit()
conn.close()

print("Database initialized with tables, plans, and courses.")
