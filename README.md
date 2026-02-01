Here is a professional **README.md** file tailored specifically for **SchoolSync Pro**.

It includes setup instructions, the tech stack, environment variable configuration, and deployment steps for Render.

***

# 🎓 SchoolSync Pro

![Flask](https://img.shields.io/badge/Flask-2.3-black?style=flat&logo=flask)
![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat&logo=python)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791?style=flat&logo=postgresql)
![Tailwind](https://img.shields.io/badge/Tailwind-CSS-38B2AC?style=flat&logo=tailwind-css)

A modern, secure, and feature-rich **Student Management System** built with Flask. It features a premium "Royal Glassmorphism" UI, Two-Factor Authentication (2FA), bulk data import, and advanced analytics.

---

## ✨ Features

### 🔐 Security & Auth
*   **Secure Login:** Role-based access control (Admin/Super Admin).
*   **Two-Factor Authentication (2FA):** Support for **Email OTP** (Gmail) and **SMS OTP** (Twilio).
*   **Rate Limiting:** Protects against brute-force attacks.
*   **CSRF Protection:** Secure forms and API requests.

### 📊 Dashboard & Management
*   **Student CRUD:** Add, Edit, View, and Delete student records.
*   **Bulk Import:** Upload students via **CSV** or **Excel** with auto-validation.
*   **Advanced Filters:** Filter by Program, Hall, Gender, Enrollment Year, and more.
*   **Live Analytics:** Real-time stats on enrollment, active students, and demographics.

### 🎨 UI / UX
*   **Glassmorphism Theme:** Premium Dark Blue & Gold aesthetic with glass effects.
*   **Theme Switcher:** Toggle between Dark Mode and Light Mode.
*   **Responsive:** Fully mobile-friendly interface with Tailwind CSS.

---

## 🛠️ Tech Stack

*   **Backend:** Python, Flask, Gunicorn
*   **Database:** PostgreSQL (Production via Neon.tech) / SQLite (Local Dev)
*   **ORM:** SQLAlchemy
*   **Frontend:** HTML5, Tailwind CSS, JavaScript, Material Icons
*   **Deployment:** Render.com

---

## 🚀 Local Installation

Follow these steps to run the project on your machine.

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/schoolsync.git
cd schoolsync
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a file named `.env` in the root directory and add the following:

```ini
# App Settings
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your_secure_random_key_here

# Database (Leave blank to use local SQLite, or add Neon URL)
DATABASE_URL=

# Email Settings (Required for 2FA)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_DEFAULT_SENDER=your_email@gmail.com

# SMS Settings (Optional - Twilio)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
```

### 5. Initialize Database
This creates the tables and the default **Admin** user.
```bash
flask init-db
```

### 6. Run the App
```bash
python app.py
```
Visit `http://127.0.0.1:5000` in your browser.

> **Default Login:**
> *   **Username:** `admin`
> *   **Password:** `Admin@123`

---

## 🌐 Deployment (Railway.com)

This app is optimized for deployment on **Render**.

1.  Push your code to **GitHub**.
2.  Log in to [https://railway.com/).
3.  Click **New +** -> **Web Service**.
4.  Connect your GitHub repository.
5.  **Settings:**
    *   **Runtime:** Python 3
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `gunicorn app:app`
6.  **Environment Variables:**
    *   Copy all keys from your local `.env` into Render's Environment Variables section.
    *   Ensure `DATABASE_URL` is set to your **Neon.tech** (PostgreSQL) connection string.

---

## 📂 Project Structure

```text
schoolsync/
├── app.py              # Main application entry point
├── auth.py             # Authentication routes & 2FA logic
├── config.py           # Configuration (Dev/Prod/DB)
├── models.py           # SQLAlchemy Database Models
├── routes.py           # Core application routes
├── utils.py            # Helper functions (OTP generation)
├── requirements.txt    # Python dependencies
├── .env                # Environment variables (Ignored by Git)
├── static/             # CSS, Images, Favicon, Uploads
└── templates/          # HTML Templates (Base, Login, Dashboard)
```

---

## 🤝 Contributing

1.  Fork the project.
2.  Create your feature branch (`git checkout -b feature/AmazingFeature`).
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4.  Push to the branch (`git push origin feature/AmazingFeature`).
5.  Open a Pull Request.

---

## 📝 License


Distributed under the MIT License. See `LICENSE` for more information.
