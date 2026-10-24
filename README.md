# 🎒 ShareSphere — Campus Item Sharing Platform

ShareSphere is a secure campus peer-to-peer item sharing and borrowing platform built with **Streamlit** and backed by **PostgreSQL (Supabase)** with local **SQLite** fallback.

---

## 🚀 Features

- **Student Authentication:** Secure campus domain verification and scrypt-based password hashing.
- **Item Listings:** List, search, filter, and manage campus items with fee structures and security deposits.
- **Borrowing Workflow:** Request, accept, reject, and return items with status tracking.
- **Escrow & Refund Simulation:** Track demo security deposits, safe returns, item damage reporting, and disputes.
- **Hybrid Database Backend:** Connects to PostgreSQL (Supabase) in production / cloud and seamlessly falls back to local SQLite for offline development.

---

## 🛠️ Tech Stack

- **Frontend & App:** [Streamlit](https://streamlit.io/)
- **Database:** [Supabase PostgreSQL](https://supabase.com/) & [SQLite](https://sqlite.org/)
- **Driver:** [Psycopg 3](https://www.psycopg.org/psycopg3/)
- **Environment Management:** Python `dotenv` & Streamlit Secrets

---

## 📦 Local Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Grandhisahasra123/ShareSphere.git
   cd ShareSphere
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # Linux / macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables (optional for local PostgreSQL):**
   Create a `.env` file in the project root:
   ```env
   DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@[YOUR-SUPABASE-HOST]:5432/postgres?sslmode=require
   ```
   *(If omitted, ShareSphere automatically operates on the local `sharesphere.db` SQLite database).*

5. **Run the Streamlit app:**
   ```bash
   streamlit run app.py
   ```

---

## ☁️ Streamlit Community Cloud Deployment

1. Go to [Streamlit Community Cloud](https://share.streamlit.io/) and log in with your GitHub account.
2. Click **New app**.
3. Select your repository: `Grandhisahasra123/ShareSphere`.
4. Set the branch to `main` and main file path to `app.py`.
5. Open **Advanced Settings** -> **Secrets**.
6. Add your Supabase connection string:
   ```toml
   DATABASE_URL = "postgresql://postgres:[YOUR-PASSWORD]@[YOUR-SUPABASE-HOST]:5432/postgres?sslmode=require"
   ```
7. Click **Deploy!**
