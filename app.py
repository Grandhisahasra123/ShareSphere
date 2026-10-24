import hashlib
import hmac
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
from db_backend import (
    get_db_connection,
    init_database,
    is_postgres,
    DBIntegrityError,
    DBError,
)

st.set_page_config(
    page_title="ShareSphere | Campus Item Sharing",
    page_icon="🎒",
    layout="wide",
)

# ---------------------------------------------------------
# Custom Modern UI Styling (Dark Navy & Teal Theme)
# Inspired by contemporary e-commerce product platforms
# ---------------------------------------------------------
st.markdown("""
<style>
/* Main App Background & Typography */
.stApp {
    background-color: #0B1120;
    color: #E2E8F0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
}

/* Headings */
h1, h2, h3, h4, h5 {
    color: #F8FAFC !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}

/* Sidebar Styling */
section[data-testid="stSidebar"] {
    background-color: #0F172A;
    border-right: 1px solid #1E293B;
}

/* Buttons */
.stButton > button {
    background-color: #0D9488;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.45rem 1rem;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.stButton > button:hover {
    background-color: #14B8A6;
    color: #FFFFFF;
    border: none;
    box-shadow: 0 4px 14px rgba(13, 148, 136, 0.35);
    transform: translateY(-1px);
}

.stButton > button:active {
    transform: translateY(0);
}

/* Secondary Button styling */
.secondary-btn button {
    background-color: #1E293B !important;
    color: #CBD5E1 !important;
    border: 1px solid #334155 !important;
}
.secondary-btn button:hover {
    background-color: #334155 !important;
    color: #F8FAFC !important;
    box-shadow: none !important;
}

/* Card and Container wrapper */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #111827;
    border: 1px solid #1E293B;
    border-radius: 12px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
    padding: 0.2rem;
}

div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: #334155;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}

/* Input Fields */
.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] {
    background-color: #1E293B !important;
    color: #F8FAFC !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
}

.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
    border-color: #0D9488 !important;
    box-shadow: 0 0 0 1px #0D9488 !important;
}

/* Tabs */
button[data-baseweb="tab"] {
    color: #94A3B8 !important;
    font-weight: 500 !important;
    padding: 10px 16px !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #14B8A6 !important;
    border-bottom-color: #14B8A6 !important;
    font-weight: 600 !important;
}

/* Dividers */
hr {
    border-color: #1E293B !important;
    margin: 1.2rem 0 !important;
}

/* Price Highlight Card */
.price-pill {
    background: rgba(13, 148, 136, 0.12);
    border: 1px solid rgba(20, 184, 166, 0.3);
    color: #5EEAD4;
    padding: 4px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 0.95rem;
    display: inline-block;
}

.deposit-pill {
    background: rgba(99, 102, 241, 0.12);
    border: 1px solid rgba(99, 102, 241, 0.3);
    color: #C7D2FE;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
    display: inline-block;
}

/* User account chip in sidebar */
.user-profile-box {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------
DB_PATH = Path(__file__).resolve().parent / "sharesphere.db"
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64

# Exactly FOUR Primary Navigation Sections
PAGES = [
    "Browse Items",
    "List an Item",
    "My Borrowings",
    "Requests",
]

STATUS_PENDING = "Pending"
STATUS_ACCEPTED = "Accepted"
STATUS_REJECTED = "Rejected"
STATUS_RETURNED = "Returned"
STATUS_CANCELLED = "Cancelled"

PAYMENT_UNPAID = "Unpaid"
PAYMENT_PAID = "Paid"

RETURN_SAFE = "Safe Return"
RETURN_DAMAGE = "Damage Reported"
RETURN_DISPUTED = "Disputed"


# ---------------------------------------------------------
# Database Helpers & Idempotent Schema Migration
# (Managed by db_backend supporting Supabase PostgreSQL & SQLite)
# ---------------------------------------------------------


# ---------------------------------------------------------
# Security & Password Hashing
# ---------------------------------------------------------
def hash_password(password):
    salt = os.urandom(16)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return salt, password_hash


def verify_password(password, salt, stored_hash):
    salt = bytes(salt) if isinstance(salt, memoryview) else salt
    stored_hash = bytes(stored_hash) if isinstance(stored_hash, memoryview) else stored_hash
    check_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return hmac.compare_digest(check_hash, stored_hash)


def is_valid_email(email):
    return EMAIL_PATTERN.match(email) is not None


# ---------------------------------------------------------
# Session State & Navigation Helpers
# ---------------------------------------------------------
def init_session():
    if "student" not in st.session_state:
        st.session_state.student = None
    if "auth_errors" not in st.session_state:
        st.session_state.auth_errors = []
    if "auth_success" not in st.session_state:
        st.session_state.auth_success = ""
    if "nav_page" not in st.session_state or st.session_state.nav_page not in PAGES:
        st.session_state.nav_page = "Browse Items"
    if "last_listed_item" not in st.session_state:
        st.session_state.last_listed_item = None
    if "list_errors" not in st.session_state:
        st.session_state.list_errors = []
    if "active_dialog" not in st.session_state:
        st.session_state.active_dialog = None
    if "dialog_req_id" not in st.session_state:
        st.session_state.dialog_req_id = None


def navigate_to(page_name):
    if page_name in PAGES:
        st.session_state.nav_page = page_name
        st.session_state.nav_page_selector = page_name


def is_logged_in():
    student = st.session_state.get("student")
    if not isinstance(student, dict):
        return False
    return bool(student.get("id") and student.get("name") and student.get("email"))


def logged_in_student():
    student = st.session_state.get("student")
    if not isinstance(student, dict) or not student.get("id"):
        return None
    return student


def logout_student():
    st.session_state.student = None
    st.session_state.auth_errors = []
    st.session_state.auth_success = "You have been logged out. Please log in again."
    st.session_state.nav_page = "Browse Items"
    st.session_state.nav_page_selector = "Browse Items"


# ---------------------------------------------------------
# Authentication Handlers
# ---------------------------------------------------------
def register_student():
    name = st.session_state.get("register_name", "").strip()
    email = st.session_state.get("register_email", "").strip().lower()
    password = st.session_state.get("register_password", "")
    confirm = st.session_state.get("register_confirm", "")

    errors = []
    if not name:
        errors.append("Student Name is required.")
    if not email:
        errors.append("Student Email is required.")
    elif not is_valid_email(email):
        errors.append("Enter a valid email address (e.g. name@college.edu).")
    if not password:
        errors.append("Password is required.")
    if not confirm:
        errors.append("Confirm Password is required.")
    if password and confirm and password != confirm:
        errors.append("Password and Confirm Password must match.")

    st.session_state.auth_errors = errors
    st.session_state.auth_success = ""
    if errors:
        return

    salt, password_hash = hash_password(password)
    connection = get_db_connection()
    try:
        connection.execute(
            """
            INSERT INTO students (name, email, password_salt, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (name, email, salt, password_hash),
        )
        connection.commit()
    except DBIntegrityError:
        st.session_state.auth_errors = [
            "That email is already registered. Try logging in instead."
        ]
        return
    finally:
        connection.close()

    st.session_state.auth_success = (
        "Account created successfully! You can now log in."
    )


def login_student():
    email = st.session_state.get("login_email", "").strip().lower()
    password = st.session_state.get("login_password", "")

    errors = []
    if not email or not password:
        errors.append("Email and password are required.")
        st.session_state.auth_errors = errors
        st.session_state.auth_success = ""
        return

    connection = get_db_connection()
    row = connection.execute(
        """
        SELECT id, name, email, password_salt, password_hash
        FROM students
        WHERE email = ?
        """,
        (email,),
    ).fetchone()
    connection.close()

    if row is None or not verify_password(
        password, row["password_salt"], row["password_hash"]
    ):
        st.session_state.auth_errors = [
            "Invalid email or password. Please try again."
        ]
        st.session_state.auth_success = ""
        st.session_state.student = None
        return

    st.session_state.student = {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
    }
    st.session_state.auth_errors = []
    st.session_state.auth_success = ""
    st.session_state.nav_page = "Browse Items"
    st.session_state.nav_page_selector = "Browse Items"


def show_auth_pages():
    _, center_col, _ = st.columns([1, 1.4, 1])
    with center_col:
        with st.container(border=True):
            st.title("🎒 ShareSphere")
            st.caption("Campus Peer-to-Peer Item Sharing Platform")

            login_tab, register_tab = st.tabs(["Log In", "Create Account"])

            with login_tab:
                with st.form("login_form", clear_on_submit=False):
                    st.text_input("Student Email", placeholder="name@college.edu", key="login_email")
                    st.text_input("Password", type="password", key="login_password")
                    st.form_submit_button("Log In", on_click=login_student)

            with register_tab:
                with st.form("register_form", clear_on_submit=True):
                    st.text_input("Student Name", placeholder="e.g. Alex Sharma", key="register_name")
                    st.text_input("Student Email", placeholder="name@college.edu", key="register_email")
                    st.text_input("Password", type="password", key="register_password")
                    st.text_input("Confirm Password", type="password", key="register_confirm")
                    st.form_submit_button("Create Account", on_click=register_student)

            for error in st.session_state.auth_errors:
                st.error(error)
            if st.session_state.auth_success:
                st.success(st.session_state.auth_success)


# ---------------------------------------------------------
# Formatting, Calculations & UI Helpers
# ---------------------------------------------------------
def format_rupees(amount):
    if amount is None:
        return "₹0"
    if float(amount) == int(amount):
        return f"₹{int(amount)}"
    return f"₹{amount:.2f}"


def format_fee(fee_type, amount):
    money = format_rupees(amount)
    if fee_type == "Fixed Fee":
        return f"{money} fixed fee"
    return f"{money} / day"


def format_deposit(amount):
    return f"{format_rupees(amount)} deposit"


def calculate_borrowing_fee(fee_type, fee_amount, days):
    if fee_type == "Per-Day Fee":
        return fee_amount * days
    return fee_amount


def calculate_late_fee(fee_type, fee_amount, requested_days, paid_at_str, deposit):
    if not paid_at_str:
        return 0, 0.0
    try:
        paid_at = datetime.strptime(paid_at_str[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0, 0.0
    due_date = paid_at + timedelta(days=requested_days)
    now = datetime.now()
    if now <= due_date:
        return 0, 0.0
    overdue_days = (now - due_date).days
    if overdue_days <= 0:
        return 0, 0.0
    daily_rate = fee_amount if fee_type == "Per-Day Fee" else (fee_amount / max(requested_days, 1))
    late_fee = min(overdue_days * daily_rate, deposit)
    return overdue_days, late_fee


def render_status_badge(status, payment_status=None, return_condition=None):
    """Generates a polished startup-quality pill badge for any state."""
    # Custom state overrides
    if status == STATUS_ACCEPTED:
        if return_condition == RETURN_DAMAGE:
            label, border, bg, text = "Damage Claim", "#F97316", "rgba(249, 115, 22, 0.15)", "#FDBA74"
        elif return_condition == RETURN_DISPUTED:
            label, border, bg, text = "Disputed", "#EF4444", "rgba(239, 68, 68, 0.15)", "#FCA5A5"
        elif payment_status == PAYMENT_PAID:
            label, border, bg, text = "Paid · Active Loan", "#10B981", "rgba(16, 185, 129, 0.15)", "#6EE7B7"
        else:
            label, border, bg, text = "Accepted · Awaiting Payment", "#0D9488", "rgba(13, 148, 136, 0.15)", "#5EEAD4"
    elif status == STATUS_RETURNED:
        label, border, bg, text = "Returned & Closed", "#6366F1", "rgba(99, 102, 241, 0.15)", "#C7D2FE"
    elif status == STATUS_PENDING:
        label, border, bg, text = "Pending Owner Approval", "#F59E0B", "rgba(245, 158, 11, 0.15)", "#FDE68A"
    elif status == STATUS_REJECTED:
        label, border, bg, text = "Rejected", "#EF4444", "rgba(239, 68, 68, 0.15)", "#FECDD3"
    elif status == STATUS_CANCELLED:
        label, border, bg, text = "Cancelled", "#64748B", "rgba(100, 116, 139, 0.15)", "#CBD5E1"
    elif status == "Available":
        label, border, bg, text = "Available", "#0D9488", "rgba(13, 148, 136, 0.15)", "#5EEAD4"
    elif status == "Currently Borrowed":
        label, border, bg, text = "Currently Borrowed", "#64748B", "rgba(100, 116, 139, 0.15)", "#94A3B8"
    else:
        label, border, bg, text = status, "#64748B", "rgba(100, 116, 139, 0.15)", "#CBD5E1"

    return (
        f'<span style="background-color: {bg}; color: {text}; border: 1px solid {border}; '
        f'padding: 3px 10px; border-radius: 9999px; font-size: 0.73rem; font-weight: 600; '
        f'text-transform: uppercase; letter-spacing: 0.04em; display: inline-block;">'
        f'{label}</span>'
    )


# ---------------------------------------------------------
# Core Data Access Queries
# ---------------------------------------------------------
def row_to_dict(row):
    """Converts a sqlite3.Row or mapping to a standard python dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def load_saved_items(owner_student_id=None):
    connection = get_db_connection()
    if owner_student_id is None:
        rows = connection.execute(
            """
            SELECT items.id, items.name, items.description, items.fee_type,
                   items.fee_amount, items.deposit, items.owner_student_id,
                   items.created_at, items.currently_borrowed, items.estimated_price,
                   students.name AS owner_name, students.email AS owner_email
            FROM items
            JOIN students ON students.id = items.owner_student_id
            ORDER BY items.created_at DESC
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT items.id, items.name, items.description, items.fee_type,
                   items.fee_amount, items.deposit, items.owner_student_id,
                   items.created_at, items.currently_borrowed, items.estimated_price,
                   students.name AS owner_name, students.email AS owner_email
            FROM items
            JOIN students ON students.id = items.owner_student_id
            WHERE items.owner_student_id = ?
            ORDER BY items.created_at DESC
            """,
            (owner_student_id,),
        ).fetchall()
    connection.close()
    return [row_to_dict(row) for row in rows]


def load_pending_request_item_ids(borrower_student_id):
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT item_id
        FROM borrowing_requests
        WHERE borrower_student_id = ? AND status = ?
        """,
        (borrower_student_id, STATUS_PENDING),
    ).fetchall()
    connection.close()
    return {row["item_id"] for row in rows}


def load_borrowing_requests(student_id, as_owner=False):
    connection = get_db_connection()
    if as_owner:
        rows = connection.execute(
            """
            SELECT requests.id, requests.item_id, requests.requested_days,
                   requests.borrowing_fee, requests.refundable_deposit,
                   requests.status, requests.created_at, requests.payment_status,
                   requests.terms_accepted_at, requests.paid_at, requests.return_requested_at,
                   requests.return_condition, requests.damage_notes, requests.damage_deduction,
                   requests.borrower_response, requests.refund_amount, requests.refunded_at,
                   requests.dispute_reason,
                   items.name AS item_name, items.fee_type, items.fee_amount,
                   borrowers.name AS borrower_name, borrowers.email AS borrower_email,
                   pmt.total_paid, pmt.refund_status, pmt.paid_at AS payment_timestamp
            FROM borrowing_requests AS requests
            JOIN items ON items.id = requests.item_id
            JOIN students AS borrowers ON borrowers.id = requests.borrower_student_id
            LEFT JOIN demo_payments AS pmt ON pmt.request_id = requests.id
            WHERE requests.owner_student_id = ?
            ORDER BY requests.created_at DESC
            """,
            (student_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT requests.id, requests.item_id, requests.requested_days,
                   requests.borrowing_fee, requests.refundable_deposit,
                   requests.status, requests.created_at, requests.payment_status,
                   requests.terms_accepted_at, requests.paid_at, requests.return_requested_at,
                   requests.return_condition, requests.damage_notes, requests.damage_deduction,
                   requests.borrower_response, requests.refund_amount, requests.refunded_at,
                   requests.dispute_reason,
                   items.name AS item_name, items.fee_type, items.fee_amount,
                   owners.name AS owner_name, owners.email AS owner_email,
                   pmt.total_paid, pmt.refund_status, pmt.paid_at AS payment_timestamp
            FROM borrowing_requests AS requests
            JOIN items ON items.id = requests.item_id
            JOIN students AS owners ON owners.id = requests.owner_student_id
            LEFT JOIN demo_payments AS pmt ON pmt.request_id = requests.id
            WHERE requests.borrower_student_id = ?
            ORDER BY requests.created_at DESC
            """,
            (student_id,),
        ).fetchall()
    connection.close()
    return [row_to_dict(row) for row in rows]


def load_student_metrics(student_id):
    """Loads activity metrics for compact account display."""
    connection = get_db_connection()
    listed_count = connection.execute(
        "SELECT COUNT(*) FROM items WHERE owner_student_id = ?", (student_id,)
    ).fetchone()[0]
    incoming_count = connection.execute(
        "SELECT COUNT(*) FROM borrowing_requests WHERE owner_student_id = ? AND status = ?",
        (student_id, STATUS_PENDING),
    ).fetchone()[0]
    borrowing_active = connection.execute(
        "SELECT COUNT(*) FROM borrowing_requests WHERE borrower_student_id = ? AND status = ? AND payment_status = ?",
        (student_id, STATUS_ACCEPTED, PAYMENT_PAID),
    ).fetchone()[0]
    connection.close()
    return {
        "items_listed": listed_count,
        "requests_received": incoming_count,
        "borrowing_active": borrowing_active,
    }


# ---------------------------------------------------------
# Server-Side Actions & Business Logic
# ---------------------------------------------------------
def create_borrowing_request(item_id, days):
    student = logged_in_student()
    if student is None:
        st.toast("Please log in first.", icon="⚠️")
        return

    try:
        days = int(days)
    except (TypeError, ValueError):
        st.toast("Requested days must be a positive integer.", icon="⚠️")
        return
    if days < 1:
        st.toast("Requested days must be at least 1.", icon="⚠️")
        return

    connection = get_db_connection()
    try:
        item = connection.execute(
            """
            SELECT id, fee_type, fee_amount, deposit, owner_student_id, currently_borrowed
            FROM items WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

        if item is None:
            st.toast("Item not found.", icon="❌")
            return
        if item["owner_student_id"] == student["id"]:
            st.toast("You cannot request your own item.", icon="⚠️")
            return
        if int(item["currently_borrowed"] or 0) == 1:
            st.toast("This item is currently on loan.", icon="⚠️")
            return

        existing = connection.execute(
            """
            SELECT id FROM borrowing_requests
            WHERE item_id = ? AND borrower_student_id = ? AND status = ?
            """,
            (item_id, student["id"], STATUS_PENDING),
        ).fetchone()
        if existing:
            st.toast("You already have a pending request for this item.", icon="⚠️")
            return

        borrowing_fee = calculate_borrowing_fee(item["fee_type"], item["fee_amount"], days)
        connection.execute(
            """
            INSERT INTO borrowing_requests (
                id, item_id, borrower_student_id, owner_student_id,
                requested_days, borrowing_fee, refundable_deposit,
                status, created_at, payment_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            """,
            (
                str(uuid.uuid4()),
                item_id,
                student["id"],
                item["owner_student_id"],
                days,
                borrowing_fee,
                item["deposit"],
                STATUS_PENDING,
                PAYMENT_UNPAID,
            ),
        )
        connection.commit()
        st.toast("Borrowing request sent to owner!", icon="✅")
    except DBIntegrityError:
        st.toast("A pending request for this item already exists.", icon="⚠️")
    finally:
        connection.close()


def accept_borrowing_request(request_id):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        request = connection.execute(
            """
            SELECT id, item_id, borrower_student_id, owner_student_id, status
            FROM borrowing_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()

        if request is None:
            connection.execute("ROLLBACK")
            st.toast("Request not found.", icon="❌")
            return
        if request["owner_student_id"] != student["id"]:
            connection.execute("ROLLBACK")
            st.toast("Only the item owner can accept this request.", icon="🚫")
            return
        if request["status"] != STATUS_PENDING:
            connection.execute("ROLLBACK")
            st.toast("Only pending requests can be accepted.", icon="⚠️")
            return

        updated_item = connection.execute(
            """
            UPDATE items SET currently_borrowed = 1
            WHERE id = ? AND currently_borrowed = 0
            """,
            (request["item_id"],),
        )
        if updated_item.rowcount != 1:
            connection.execute("ROLLBACK")
            st.toast("Item is already marked currently borrowed.", icon="⚠️")
            return

        connection.execute(
            """
            UPDATE borrowing_requests
            SET status = ?, payment_status = ?
            WHERE id = ? AND owner_student_id = ? AND status = ?
            """,
            (STATUS_ACCEPTED, PAYMENT_UNPAID, request_id, student["id"], STATUS_PENDING),
        )
        connection.execute("COMMIT")
        st.toast("Request accepted. Borrower notified to pay demo fee & deposit.", icon="✅")
    except DBError:
        connection.execute("ROLLBACK")
        st.toast("Could not accept request. Please try again.", icon="❌")
    finally:
        connection.close()


def reject_borrowing_request(request_id):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    try:
        res = connection.execute(
            """
            UPDATE borrowing_requests
            SET status = ?
            WHERE id = ? AND owner_student_id = ? AND status = ?
            """,
            (STATUS_REJECTED, request_id, student["id"], STATUS_PENDING),
        )
        connection.commit()
        if res.rowcount == 1:
            st.toast("Borrowing request rejected.", icon="ℹ️")
    finally:
        connection.close()


def cancel_borrowing_request(request_id):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        req = connection.execute(
            """
            SELECT id, item_id, borrower_student_id, owner_student_id, status, payment_status,
                   borrowing_fee, refundable_deposit
            FROM borrowing_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()

        if req is None:
            connection.execute("ROLLBACK")
            st.toast("Request not found.", icon="❌")
            return

        is_borrower = (req["borrower_student_id"] == student["id"])
        is_owner = (req["owner_student_id"] == student["id"])

        if not (is_borrower or is_owner):
            connection.execute("ROLLBACK")
            st.toast("Unauthorized to cancel this request.", icon="🚫")
            return

        # Case 1: Pending request (borrower can cancel)
        if req["status"] == STATUS_PENDING:
            if not is_borrower:
                connection.execute("ROLLBACK")
                st.toast("Only borrower can cancel a pending request (owners can reject it).", icon="⚠️")
                return
            connection.execute(
                "UPDATE borrowing_requests SET status = ? WHERE id = ?",
                (STATUS_CANCELLED, request_id),
            )
            connection.execute("COMMIT")
            st.toast("Borrowing request cancelled.", icon="ℹ️")
            return

        # Case 2: Accepted & Unpaid (either borrower or owner can cancel before payment)
        if req["status"] == STATUS_ACCEPTED and req["payment_status"] == PAYMENT_UNPAID:
            connection.execute(
                "UPDATE borrowing_requests SET status = ? WHERE id = ?",
                (STATUS_CANCELLED, request_id),
            )
            # Restore item availability
            connection.execute(
                "UPDATE items SET currently_borrowed = 0 WHERE id = ?",
                (req["item_id"],),
            )
            connection.execute("COMMIT")
            st.toast("Request cancelled. Item availability restored.", icon="ℹ️")
            return

        # Case 3: Accepted & Paid (Handover cancellation with 100% full demo refund)
        if req["status"] == STATUS_ACCEPTED and req["payment_status"] == PAYMENT_PAID:
            pmt = connection.execute(
                "SELECT total_paid FROM demo_payments WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            total_paid = pmt["total_paid"] if pmt else (req["borrowing_fee"] + req["refundable_deposit"])
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            connection.execute(
                """
                UPDATE borrowing_requests
                SET status = ?, return_condition = 'Handover Cancelled',
                    refund_amount = ?, refunded_at = ?
                WHERE id = ?
                """,
                (STATUS_CANCELLED, total_paid, now_str, request_id),
            )
            connection.execute(
                """
                UPDATE demo_payments
                SET refund_amount = ?, refund_status = 'Full Demo Refund (Handover Cancelled)',
                    refunded_at = ?, refund_notes = 'Order cancelled before completion; full demo refund issued.'
                WHERE request_id = ?
                """,
                (total_paid, now_str, request_id),
            )
            connection.execute(
                "UPDATE items SET currently_borrowed = 0 WHERE id = ?",
                (req["item_id"],),
            )
            connection.execute("COMMIT")
            st.toast(f"Order cancelled. Full demo refund of {format_rupees(total_paid)} processed.", icon="ℹ️")
            return

        connection.execute("ROLLBACK")
        st.toast("This request cannot be cancelled in its current state.", icon="⚠️")
    except DBError:
        connection.execute("ROLLBACK")
        st.toast("Failed to cancel request. Please try again.", icon="❌")
    finally:
        connection.close()


def execute_demo_payment(request_id):
    student = logged_in_student()
    if student is None:
        st.toast("Please log in first.", icon="⚠️")
        return False, "Not logged in"

    connection = get_db_connection()
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        req = connection.execute(
            """
            SELECT id, item_id, borrower_student_id, owner_student_id,
                   borrowing_fee, refundable_deposit, status, payment_status
            FROM borrowing_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()

        if req is None:
            connection.execute("ROLLBACK")
            return False, "Request not found."
        if req["borrower_student_id"] != student["id"]:
            connection.execute("ROLLBACK")
            return False, "Authorization error: Only the borrower can complete payment."
        if req["status"] != STATUS_ACCEPTED:
            connection.execute("ROLLBACK")
            return False, "Request has not been accepted by the owner."
        if req["payment_status"] == PAYMENT_PAID:
            connection.execute("ROLLBACK")
            return False, "Payment has already been completed for this request."

        if not st.session_state.get(f"agree_terms_{request_id}"):
            connection.execute("ROLLBACK")
            return False, "You must accept the terms and conditions before completing demo payment."

        # Check existing payment record
        existing_pmt = connection.execute(
            "SELECT id FROM demo_payments WHERE request_id = ?", (request_id,)
        ).fetchone()
        if existing_pmt:
            connection.execute("ROLLBACK")
            return False, "A demo payment record already exists for this request."

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_paid = req["borrowing_fee"] + req["refundable_deposit"]

        # Insert demo payment record
        payment_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO demo_payments (
                id, request_id, borrower_student_id, owner_student_id,
                borrowing_fee, refundable_deposit, total_paid,
                payment_type, payment_status, paid_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Demo Payment', 'Completed', ?)
            """,
            (
                payment_id,
                request_id,
                student["id"],
                req["owner_student_id"],
                req["borrowing_fee"],
                req["refundable_deposit"],
                total_paid,
                now_str,
            ),
        )

        # Update request
        connection.execute(
            """
            UPDATE borrowing_requests
            SET payment_status = ?, terms_accepted_at = ?, paid_at = ?
            WHERE id = ? AND borrower_student_id = ?
            """,
            (PAYMENT_PAID, now_str, now_str, request_id, student["id"]),
        )

        connection.execute("COMMIT")
        st.toast(f"Demo Payment of {format_rupees(total_paid)} successful! Loan activated.", icon="🎉")
        return True, "Success"
    except DBError as e:
        connection.execute("ROLLBACK")
        return False, f"Database error: {str(e)}"
    finally:
        connection.close()


def request_return_handover(request_id):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        res = connection.execute(
            """
            UPDATE borrowing_requests
            SET return_requested_at = ?
            WHERE id = ? AND borrower_student_id = ? AND status = ? AND payment_status = ?
            """,
            (now_str, request_id, student["id"], STATUS_ACCEPTED, PAYMENT_PAID),
        )
        connection.commit()
        if res.rowcount == 1:
            st.toast("Return handover recorded. Awaiting owner's safe return verification.", icon="📦")
    finally:
        connection.close()


def confirm_safe_return(request_id):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        req = connection.execute(
            """
            SELECT item_id, owner_student_id, status, payment_status, refundable_deposit
            FROM borrowing_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()

        if req is None or req["owner_student_id"] != student["id"]:
            connection.execute("ROLLBACK")
            st.toast("Authorization error: Only the owner can confirm return.", icon="🚫")
            return
        if req["status"] != STATUS_ACCEPTED:
            connection.execute("ROLLBACK")
            st.toast("Only accepted loans can be marked returned.", icon="⚠️")
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        deposit_refund = req["refundable_deposit"]

        # Update request
        connection.execute(
            """
            UPDATE borrowing_requests
            SET status = ?, return_condition = ?, refund_amount = ?, refunded_at = ?
            WHERE id = ? AND owner_student_id = ?
            """,
            (STATUS_RETURNED, RETURN_SAFE, deposit_refund, now_str, request_id, student["id"]),
        )

        # Update demo payments refund
        connection.execute(
            """
            UPDATE demo_payments
            SET refund_amount = ?, refund_status = 'Demo Refund Completed',
                refunded_at = ?, refund_notes = 'Full deposit refunded upon safe return.'
            WHERE request_id = ?
            """,
            (deposit_refund, now_str, request_id),
        )

        # Free the item
        connection.execute(
            "UPDATE items SET currently_borrowed = 0 WHERE id = ?", (req["item_id"],)
        )
        connection.execute("COMMIT")
        st.toast(f"Item returned safely. Full deposit of {format_rupees(deposit_refund)} demo-refunded!", icon="✅")
    except DBError:
        connection.execute("ROLLBACK")
        st.toast("Could not complete return. Please try again.", icon="❌")
    finally:
        connection.close()


def report_damage_claim(request_id, damage_notes, deduction_amount):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    try:
        req = connection.execute(
            "SELECT refundable_deposit, owner_student_id FROM borrowing_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if not req or req["owner_student_id"] != student["id"]:
            st.toast("Unauthorized action.", icon="🚫")
            return

        if deduction_amount <= 0 or deduction_amount > req["refundable_deposit"]:
            st.toast(f"Deduction must be between ₹1 and {format_rupees(req['refundable_deposit'])}.", icon="⚠️")
            return

        connection.execute(
            """
            UPDATE borrowing_requests
            SET return_condition = ?, damage_notes = ?, damage_deduction = ?
            WHERE id = ? AND owner_student_id = ?
            """,
            (RETURN_DAMAGE, damage_notes.strip(), deduction_amount, request_id, student["id"]),
        )
        connection.commit()
        st.toast("Damage report submitted. Borrower has been notified to review or dispute.", icon="⚠️")
    finally:
        connection.close()


def borrower_respond_to_damage(request_id, accept_claim, response_notes=""):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        req = connection.execute(
            """
            SELECT item_id, borrower_student_id, refundable_deposit, damage_deduction, damage_notes
            FROM borrowing_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()

        if not req or req["borrower_student_id"] != student["id"]:
            connection.execute("ROLLBACK")
            st.toast("Unauthorized.", icon="🚫")
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if accept_claim:
            deduction = req["damage_deduction"]
            refund_amount = max(0.0, req["refundable_deposit"] - deduction)

            connection.execute(
                """
                UPDATE borrowing_requests
                SET status = ?, borrower_response = 'Accepted deduction',
                    refund_amount = ?, refunded_at = ?
                WHERE id = ?
                """,
                (STATUS_RETURNED, refund_amount, now_str, request_id),
            )
            connection.execute(
                """
                UPDATE demo_payments
                SET refund_amount = ?, refund_status = 'Partial Demo Refund Completed',
                    refunded_at = ?, refund_notes = ?
                WHERE request_id = ?
                """,
                (refund_amount, now_str, f"Deduction applied: ₹{deduction} ({req['damage_notes']})", request_id),
            )
            connection.execute("UPDATE items SET currently_borrowed = 0 WHERE id = ?", (req["item_id"],))
            connection.execute("COMMIT")
            st.toast(f"Deduction accepted. Net deposit of {format_rupees(refund_amount)} demo-refunded.", icon="ℹ️")
        else:
            connection.execute(
                """
                UPDATE borrowing_requests
                SET return_condition = ?, dispute_reason = ?
                WHERE id = ?
                """,
                (RETURN_DISPUTED, response_notes.strip(), request_id),
            )
            connection.execute("COMMIT")
            st.toast("Dispute evidence submitted for owner review.", icon="📝")
    except DBError:
        connection.execute("ROLLBACK")
        st.toast("Action could not be saved.", icon="❌")
    finally:
        connection.close()


def resolve_dispute(request_id, agreed_refund, resolution_notes):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        req = connection.execute(
            "SELECT item_id, owner_student_id, refundable_deposit FROM borrowing_requests WHERE id = ?",
            (request_id,),
        ).fetchone()

        if not req or req["owner_student_id"] != student["id"]:
            connection.execute("ROLLBACK")
            st.toast("Unauthorized.", icon="🚫")
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agreed_refund = min(max(0.0, agreed_refund), req["refundable_deposit"])

        connection.execute(
            """
            UPDATE borrowing_requests
            SET status = ?, return_condition = 'Dispute Resolved',
                refund_amount = ?, refunded_at = ?, borrower_response = ?
            WHERE id = ?
            """,
            (STATUS_RETURNED, agreed_refund, now_str, resolution_notes, request_id),
        )
        connection.execute(
            """
            UPDATE demo_payments
            SET refund_amount = ?, refund_status = 'Dispute Resolved Refund',
                refunded_at = ?, refund_notes = ?
            WHERE request_id = ?
            """,
            (agreed_refund, now_str, resolution_notes, request_id),
        )
        connection.execute("UPDATE items SET currently_borrowed = 0 WHERE id = ?", (req["item_id"],))
        connection.execute("COMMIT")
        st.toast(f"Dispute resolved. {format_rupees(agreed_refund)} demo-refunded.", icon="✅")
    except DBError:
        connection.execute("ROLLBACK")
        st.toast("Could not save resolution.", icon="❌")
    finally:
        connection.close()


def remove_listed_item(item_id):
    student = logged_in_student()
    if student is None:
        return

    connection = get_db_connection()
    try:
        item = connection.execute(
            "SELECT currently_borrowed FROM items WHERE id = ? AND owner_student_id = ?",
            (item_id, student["id"]),
        ).fetchone()
        if item is None:
            return
        if int(item["currently_borrowed"] or 0) == 1:
            st.toast("You cannot remove an item while it is currently borrowed.", icon="⚠️")
            return

        request_count = connection.execute(
            "SELECT COUNT(*) FROM borrowing_requests WHERE item_id = ?",
            (item_id,),
        ).fetchone()[0]
        if request_count > 0:
            st.toast("Cannot remove an item that has borrowing request records.", icon="⚠️")
            return

        connection.execute("DELETE FROM items WHERE id = ? AND owner_student_id = ?", (item_id, student["id"]))
        connection.commit()
        st.toast("Listing removed successfully.", icon="🗑️")
    except DBIntegrityError:
        st.toast("Cannot remove this item because it is referenced in borrowing records.", icon="⚠️")
    finally:
        connection.close()


def validate_listing(name, description, fee, deposit):
    errors = []
    if not name.strip():
        errors.append("Item Name is required.")
    if not description.strip():
        errors.append("Description is required.")
    if fee <= 0:
        errors.append("Borrowing Fee must be greater than zero.")
    if deposit < 0:
        errors.append("Refundable Security Deposit cannot be negative.")
    return errors


def add_listed_item():
    student = logged_in_student()
    if student is None:
        st.session_state.list_errors = ["Please log in before listing an item."]
        st.session_state.last_listed_item = None
        return

    name = st.session_state.get("list_item_name", "")
    description = st.session_state.get("list_item_description", "")
    fee_type = st.session_state.get("list_item_fee_type", "Per-Day Fee")
    fee = st.session_state.get("list_item_fee", 0.0)
    deposit = st.session_state.get("list_item_deposit", 0.0)
    estimated_price = st.session_state.get("list_item_estimated_price", 0.0)

    errors = validate_listing(name, description, fee, deposit)
    st.session_state.list_errors = errors
    if errors:
        st.session_state.last_listed_item = None
        return

    item_id = str(uuid.uuid4())
    connection = get_db_connection()
    try:
        connection.execute(
            """
            INSERT INTO items (
                id, name, description, fee_type, fee_amount, deposit,
                estimated_price, owner_student_id, created_at, currently_borrowed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 0)
            """,
            (
                item_id,
                name.strip(),
                description.strip(),
                fee_type,
                fee,
                deposit,
                estimated_price,
                student["id"],
            ),
        )
        connection.commit()
        st.session_state.last_listed_item = {
            "id": item_id,
            "name": name.strip(),
            "description": description.strip(),
            "fee_type": fee_type,
            "fee": fee,
            "deposit": deposit,
        }
        st.toast("Your item has been listed successfully!", icon="🎉")
    finally:
        connection.close()


# ---------------------------------------------------------
# Modal Dialogs: Terms & Demo Checkout, Damage, Dispute
# ---------------------------------------------------------
@st.dialog("📋 Review Terms & Complete Demo Checkout")
def show_checkout_dialog(request_id):
    student = logged_in_student()
    if student is None:
        st.error("Please log in first.")
        return

    connection = get_db_connection()
    req = connection.execute(
        """
        SELECT requests.*, items.name AS item_name, items.fee_type, items.fee_amount,
               owners.name AS owner_name
        FROM borrowing_requests AS requests
        JOIN items ON items.id = requests.item_id
        JOIN students AS owners ON owners.id = requests.owner_student_id
        WHERE requests.id = ?
        """,
        (request_id,),
    ).fetchone()
    connection.close()
    req = row_to_dict(req)

    if not req:
        st.error("Request details could not be found.")
        return
    if req["borrower_student_id"] != student["id"]:
        st.error("Only the borrower can complete payment.")
        return

    st.markdown(f"### Borrowing: **{req['item_name']}**")
    st.caption(f"Owner: **{req['owner_name']}** · Duration: **{req['requested_days']} day{'s' if req['requested_days'] != 1 else ''}**")

    # Payment Summary Breakdown
    total_payable = req["borrowing_fee"] + req["refundable_deposit"]
    with st.container(border=True):
        st.markdown("#### 💳 Payment Summary")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Borrowing Fee", format_rupees(req["borrowing_fee"]))
        with c2:
            st.metric("Refundable Deposit", format_rupees(req["refundable_deposit"]))
        with c3:
            st.metric("Total Payable", format_rupees(total_payable))

    st.warning("⚠️ **DEMO PAYMENT SANDBOX:** This application uses a simulated checkout. No real money or payment gateway is involved. Record is saved securely for testing.")

    # Terms and Conditions
    st.markdown("#### 📜 ShareSphere Student Borrowing Terms & Conditions")
    with st.expander("Read Full Terms & Policies (Required)", expanded=True):
        st.markdown("""
1. **Upfront Demo Payment:** The borrower pays the borrowing fee plus the refundable security deposit in full prior to physical item handover.
2. **Safe Return Refund:** The security deposit is eligible for a 100% full demo refund immediately upon owner confirmation that the item was returned safely without damage.
3. **Damage Reporting Safeguards:** If an owner claims item damage, they must supply descriptive evidence and a proposed deduction amount. The borrower has the right to review and accept or submit counter-evidence.
4. **Late Return Policy:** Returns past the agreed return deadline accrue additional rent daily at the agreed rate, capped reasonably at the security deposit amount.
5. **Non-Return Responsibility:** Failure to return the item triggers reminders and dispute escalation. The security deposit does not automatically waive borrower liability for returning the item.
6. **Return Disputes:** Borrowers can mark an item returned with timestamp evidence. Owners cannot withhold deposits indefinitely without an active dispute resolution.
7. **Cancellation Rights:** If the owner fails to hand over the item, the borrower is entitled to an immediate cancellation and full demo refund.
8. **Condition Verification:** Both parties are strongly advised to inspect the item and note its condition during handover and return.
        """)

    terms_agreed = st.checkbox(
        "I have read and agree to the ShareSphere Student Borrowing Terms & Conditions, and I understand this is a simulated demo payment.",
        key=f"agree_terms_{request_id}",
    )

    pay_col1, pay_col2 = st.columns([2, 1])
    with pay_col1:
        if st.button("Confirm Demo Payment", key=f"btn_pay_{request_id}", disabled=not terms_agreed):
            ok, msg = execute_demo_payment(request_id)
            if ok:
                st.rerun()
            else:
                st.error(msg)


@st.dialog("⚠️ Report Item Damage / Propose Deduction")
def show_damage_dialog(request_id):
    connection = get_db_connection()
    req = connection.execute(
        """
        SELECT requests.*, items.name AS item_name, borrowers.name AS borrower_name
        FROM borrowing_requests AS requests
        JOIN items ON items.id = requests.item_id
        JOIN students AS borrowers ON borrowers.id = requests.borrower_student_id
        WHERE requests.id = ?
        """,
        (request_id,),
    ).fetchone()
    connection.close()
    req = row_to_dict(req)

    if not req:
        st.error("Request not found.")
        return

    st.markdown(f"#### Damage Claim for **{req['item_name']}**")
    st.caption(f"Borrower: **{req['borrower_name']}** · Security Deposit: **{format_rupees(req['refundable_deposit'])}**")
    st.write("Disclose the condition issue and proposed deposit deduction. The borrower will be given an opportunity to review or dispute.")

    notes = st.text_area("Damage Description & Evidence Notes", placeholder="e.g. Scratched lens, missing cable...")
    deduction = st.number_input(
        f"Proposed Deduction in ₹ (Max: {format_rupees(req['refundable_deposit'])})",
        min_value=1.0,
        max_value=float(req["refundable_deposit"]),
        value=min(50.0, float(req["refundable_deposit"])),
        step=10.0,
    )

    if st.button("Submit Damage Report"):
        if not notes.strip():
            st.error("Please provide damage description notes.")
            return
        report_damage_claim(request_id, notes, deduction)
        st.rerun()


@st.dialog("📝 Submit Damage Dispute Response")
def show_dispute_dialog(request_id):
    connection = get_db_connection()
    req = connection.execute(
        "SELECT * FROM borrowing_requests WHERE id = ?", (request_id,)
    ).fetchone()
    connection.close()
    req = row_to_dict(req)

    if not req:
        st.error("Request not found.")
        return

    st.markdown("#### Dispute Owner Damage Claim")
    st.write(f"**Owner's Claim:** {req['damage_notes']}")
    st.write(f"**Proposed Deduction:** {format_rupees(req['damage_deduction'])}")
    notes = st.text_area("Your Explanation / Counter Evidence", placeholder="Explain why this deduction is inaccurate...")

    if st.button("Submit Dispute"):
        if not notes.strip():
            st.error("Please provide your explanation.")
            return
        borrower_respond_to_damage(request_id, accept_claim=False, response_notes=notes)
        st.rerun()


@st.dialog("🤝 Resolve Return Dispute")
def show_resolve_dispute_dialog(request_id):
    connection = get_db_connection()
    req = connection.execute(
        "SELECT * FROM borrowing_requests WHERE id = ?", (request_id,)
    ).fetchone()
    connection.close()
    req = row_to_dict(req)

    if not req:
        st.error("Request not found.")
        return

    st.markdown("#### Resolve Return Dispute")
    st.write(f"**Owner Claim:** {req['damage_notes']} ({format_rupees(req['damage_deduction'])})")
    st.write(f"**Borrower Response:** {req['dispute_reason']}")
    agreed_refund = st.number_input(
        f"Final Agreed Refund Amount to Borrower (Max: {format_rupees(req['refundable_deposit'])})",
        min_value=0.0,
        max_value=float(req["refundable_deposit"]),
        value=float(req["refundable_deposit"]),
        step=10.0,
    )
    notes = st.text_input("Resolution Note", value="Dispute resolved by mutual agreement.")

    if st.button("Finalize Dispute & Return"):
        resolve_dispute(request_id, agreed_refund, notes)
        st.rerun()


# ---------------------------------------------------------
# Primary Section A: Browse Items
# ---------------------------------------------------------
def show_browse_items():
    student = logged_in_student()
    st.title("Browse Campus Gear")
    st.caption("Discover textbooks, calculators, and essentials shared by fellow students on campus.")

    # Search & Category Filters
    search_col, cat_col = st.columns([3, 1])
    categories = ["All Categories", "Books", "Electronics", "Lab Equipment", "Accessories", "Other"]

    with search_col:
        query = st.text_input(
            "Search items",
            placeholder="Search by name, description, or keyword (e.g. TI-84, textbook, umbrella...)",
            label_visibility="collapsed",
        ).strip().lower()

    with cat_col:
        selected_category = st.selectbox("Category", categories, label_visibility="collapsed")

    items = load_saved_items()

    def get_category(item):
        desc = item.get("description", "") if isinstance(item, dict) else (item["description"] or "")
        text = f"{item['name']} {desc}".lower()
        if any(w in text for w in ("book", "textbook", "novel", "notes")):
            return "Books"
        if any(w in text for w in ("calculator", "laptop", "charger", "cable", "mouse", "electronics", "headphone")):
            return "Electronics"
        if any(w in text for w in ("lab", "microscope", "kit", "equipment", "meter")):
            return "Lab Equipment"
        if any(w in text for w in ("umbrella", "bag", "shoes", "bottle", "stand", "accessory")):
            return "Accessories"
        return "Other"

    # Filter by query & category
    if query:
        items = [
            it for it in items
            if query in it["name"].lower() or query in (it.get("description", "") if isinstance(it, dict) else (it["description"] or "")).lower()
        ]
    if selected_category != "All Categories":
        items = [it for it in items if get_category(it) == selected_category]

    st.caption(f"Showing **{len(items)}** listing{'s' if len(items) != 1 else ''}")

    if not items:
        with st.container(border=True):
            st.markdown("#### 🔍 No items found matching your filters")
            st.caption("Try adjusting your search terms or be the first to share an item with your campus community.")
            st.button("List an Item", key="browse_empty_btn", on_click=navigate_to, args=("List an Item",))
        return

    pending_item_ids = load_pending_request_item_ids(student["id"])
    columns = st.columns(3, gap="medium")

    for index, item in enumerate(items):
        with columns[index % 3]:
            with st.container(border=True):
                # Header & Status Badge
                is_borrowed = bool(item.get("currently_borrowed") if isinstance(item, dict) else item["currently_borrowed"])
                badge_status = (
                    "Currently Borrowed" if is_borrowed
                    else (STATUS_PENDING if item["id"] in pending_item_ids else "Available")
                )
                h1, h2 = st.columns([3, 1])
                with h1:
                    st.markdown(f"#### {item['name']}")
                    st.caption(f"Shared by **{item['owner_name']}**")
                with h2:
                    st.markdown(f"<div style='text-align:right;'>{render_status_badge(badge_status)}</div>", unsafe_allow_html=True)

                st.write(item["description"])

                # Pricing Cards
                p1, p2 = st.columns(2)
                with p1:
                    st.markdown(f"<div class='price-pill'>{format_fee(item['fee_type'], item['fee_amount'])}</div>", unsafe_allow_html=True)
                with p2:
                    st.markdown(f"<div class='deposit-pill'>+ {format_deposit(item['deposit'])}</div>", unsafe_allow_html=True)

                st.markdown("<hr style='margin: 0.8rem 0;'>", unsafe_allow_html=True)

                # Contextual Actions
                if item["owner_student_id"] == student["id"]:
                    st.caption("👤 You own this listing.")
                    st.button("Manage in 'List an Item'", key=f"manage_own_{item['id']}", on_click=navigate_to, args=("List an Item",))
                elif is_borrowed:
                    st.caption("⏳ This item is currently on loan.")
                elif item["id"] in pending_item_ids:
                    st.caption("📩 You have a pending request for this item. Track in **My Borrowings**.")
                else:
                    days_key = f"borrow_days_{item['id']}"
                    days = st.number_input(
                        "Days required",
                        min_value=1,
                        step=1,
                        value=1,
                        key=days_key,
                    )
                    calc_fee = calculate_borrowing_fee(item["fee_type"], item["fee_amount"], int(days))
                    st.caption(f"Estimated Fee: **{format_rupees(calc_fee)}** + Deposit: **{format_rupees(item['deposit'])}**")
                    if st.button("Request to Borrow", key=f"req_btn_{item['id']}"):
                        create_borrowing_request(item["id"], days)
                        st.rerun()


# ---------------------------------------------------------
# Primary Section B: List an Item
# ---------------------------------------------------------
def show_list_an_item():
    student = logged_in_student()
    st.title("List an Item")
    st.caption("Share your unused gear with campus peers. Earn small fees while helping fellow students.")

    # Listing Form
    with st.form("list_item_form", clear_on_submit=True):
        st.text_input("Item Name", placeholder="e.g. Casio fx-991EX Scientific Calculator", key="list_item_name")
        st.text_area("Description & Condition", placeholder="Describe condition, accessories included, and pickup instructions...", key="list_item_description")

        col1, col2 = st.columns(2)
        with col1:
            st.radio("Fee Pricing Method", ["Per-Day Fee", "Fixed Fee"], horizontal=True, key="list_item_fee_type")
            st.number_input("Borrowing Fee in ₹", min_value=0.0, step=5.0, format="%.2f", key="list_item_fee")
        with col2:
            st.number_input("Refundable Security Deposit in ₹", min_value=0.0, step=10.0, format="%.2f", key="list_item_deposit", help="Fully refunded to borrower upon verified safe return.")
            st.number_input("Estimated Purchase Price in ₹", min_value=0.0, step=50.0, format="%.2f", key="list_item_estimated_price", help="Optional retail reference price to guide deposit.")

        st.form_submit_button("Post Listing", on_click=add_listed_item)

    for err in st.session_state.list_errors:
        st.error(err)

    if st.session_state.last_listed_item:
        last = st.session_state.last_listed_item
        with st.container(border=True):
            st.success(f"🎉 **{last['name']}** has been posted to Browse Items!")
            st.button("View in Browse Items", key="view_browse_after_add", on_click=navigate_to, args=("Browse Items",))

    # Manage Your Existing Listings (Preserved from Home/Dashboard)
    st.markdown("---")
    st.markdown("### Manage Your Active Listings")
    st.caption("Review or remove items you have shared with the campus.")

    own_items = load_saved_items(student["id"])
    if not own_items:
        st.info("You haven't listed any items yet. Fill out the form above to post your first listing.")
        return

    cols = st.columns(3, gap="medium")
    for idx, item in enumerate(own_items):
        with cols[idx % 3]:
            with st.container(border=True):
                h1, h2 = st.columns([3, 1])
                is_borrowed = bool(item.get("currently_borrowed") if isinstance(item, dict) else item["currently_borrowed"])
                with h1:
                    st.markdown(f"#### {item['name']}")
                with h2:
                    status_text = "Currently Borrowed" if is_borrowed else "Available"
                    st.markdown(f"<div style='text-align:right;'>{render_status_badge(status_text)}</div>", unsafe_allow_html=True)

                st.write(item["description"])
                st.caption(f"Fee: **{format_fee(item['fee_type'], item['fee_amount'])}** · Deposit: **{format_deposit(item['deposit'])}**")

                if is_borrowed:
                    st.caption("🔒 Currently borrowed — cannot be removed until returned.")
                else:
                    if st.button("Remove Listing", key=f"del_item_{item['id']}"):
                        remove_listed_item(item["id"])
                        st.rerun()


# ---------------------------------------------------------
# Primary Section C: My Borrowings (Borrower View)
# ---------------------------------------------------------
def show_my_borrowings():
    student = logged_in_student()
    st.title("My Borrowings")
    st.caption("Track items you have requested, review terms, complete demo checkout, and coordinate returns.")

    borrower_requests = load_borrowing_requests(student["id"], as_owner=False)

    if not borrower_requests:
        with st.container(border=True):
            st.markdown("#### You have no borrowing requests")
            st.caption("Browse available campus items to borrow textbooks, calculators, and study gear.")
            st.button("Browse Campus Items", key="empty_borrowings_browse_btn", on_click=navigate_to, args=("Browse Items",))
        return

    # Categorize requests
    active_tab, history_tab = st.tabs(["Active Loans & Payment Actions", "Completed & Inactive"])

    with active_tab:
        active_requests = [
            r for r in borrower_requests
            if r["status"] in (STATUS_PENDING, STATUS_ACCEPTED)
        ]
        if not active_requests:
            st.info("No active loans or pending approvals.")
        else:
            for req in active_requests:
                with st.container(border=True):
                    h1, h2 = st.columns([3, 1])
                    with h1:
                        st.markdown(f"### {req['item_name']}")
                        st.caption(f"Owner: **{req['owner_name']}** ({req['owner_email']}) · Requested: {req['created_at'][:16]}")
                    with h2:
                        st.markdown(f"<div style='text-align:right;'>{render_status_badge(req['status'], req['payment_status'], req['return_condition'])}</div>", unsafe_allow_html=True)

                    # Financial & Duration Summary
                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        st.metric("Duration", f"{req['requested_days']} days")
                    with m2:
                        st.metric("Borrowing Fee", format_rupees(req["borrowing_fee"]))
                    with m3:
                        st.metric("Refundable Deposit", format_rupees(req["refundable_deposit"]))
                    with m4:
                        st.metric("Total Payable", format_rupees(req["borrowing_fee"] + req["refundable_deposit"]))

                    # Contextual borrower actions based on exact state
                    if req["status"] == STATUS_PENDING:
                        st.info("⏳ Waiting for the item owner to accept your borrowing request.")
                        if st.button("Cancel Request", key=f"borrower_cancel_{req['id']}"):
                            cancel_borrowing_request(req["id"])
                            st.rerun()

                    elif req["status"] == STATUS_ACCEPTED and req["payment_status"] == PAYMENT_UNPAID:
                        st.success("🎉 Owner accepted your request! Review the terms and complete demo checkout to activate your loan.")
                        c_pay, c_cnl = st.columns([2.5, 1])
                        with c_pay:
                            if st.button("💳 Review Terms & Complete Demo Checkout", key=f"checkout_btn_{req['id']}"):
                                show_checkout_dialog(req["id"])
                        with c_cnl:
                            if st.button("Cancel Request", key=f"borrower_cancel_unpaid_{req['id']}"):
                                cancel_borrowing_request(req["id"])
                                st.rerun()

                    elif req["status"] == STATUS_ACCEPTED and req["payment_status"] == PAYMENT_PAID:
                        # Check overdue status
                        overdue_days, late_fee = calculate_late_fee(
                            req["fee_type"], req["fee_amount"], req["requested_days"],
                            req["paid_at"], req["refundable_deposit"]
                        )

                        if overdue_days > 0:
                            st.error(f"⚠️ **OVERDUE by {overdue_days} day{'s' if overdue_days != 1 else ''}:** Accrued late fee: **{format_rupees(late_fee)}** (capped at deposit). Please return the item immediately.")
                        else:
                            st.info(f"✅ **Active Loan:** Paid on {req['paid_at'][:16]}. Coordinate handover/return with owner `{req['owner_email']}`.")

                        # Damage claim handling
                        if req["return_condition"] == RETURN_DAMAGE:
                            with st.container(border=True):
                                st.warning(f"⚠️ **Owner Reported Damage:** {req['damage_notes']}")
                                st.write(f"Proposed Deduction: **{format_rupees(req['damage_deduction'])}**")
                                c_acc, c_disp = st.columns(2)
                                with c_acc:
                                    if st.button("Accept Proposed Deduction", key=f"acc_dmg_{req['id']}"):
                                        borrower_respond_to_damage(req["id"], accept_claim=True)
                                        st.rerun()
                                with c_disp:
                                    if st.button("Dispute Damage Claim", key=f"disp_dmg_{req['id']}"):
                                        show_dispute_dialog(req["id"])
                        elif req["return_condition"] == RETURN_DISPUTED:
                            st.warning(f"⚠️ Dispute pending owner resolution. Your note: '{req['dispute_reason']}'")
                        elif bool(req.get("return_requested_at") if isinstance(req, dict) else req["return_requested_at"]):
                            st.info("📦 You marked this item as returned. Awaiting owner's safe return verification.")
                        else:
                            b_ret, b_cnl = st.columns([2, 1.5])
                            with b_ret:
                                if st.button("📦 Mark Handed Over / Initiate Return", key=f"return_btn_{req['id']}"):
                                    request_return_handover(req["id"])
                                    st.rerun()
                            with b_cnl:
                                if st.button("Cancel & Demo Refund", key=f"borrower_cancel_paid_{req['id']}", help="Cancel loan and receive full demo refund if item handover failed"):
                                    cancel_borrowing_request(req["id"])
                                    st.rerun()

    with history_tab:
        history_requests = [
            r for r in borrower_requests
            if r["status"] in (STATUS_RETURNED, STATUS_REJECTED, STATUS_CANCELLED)
        ]
        if not history_requests:
            st.info("No past borrowing history.")
        else:
            for req in history_requests:
                with st.container(border=True):
                    h1, h2 = st.columns([3, 1])
                    with h1:
                        st.markdown(f"#### {req['item_name']}")
                        st.caption(f"Owner: **{req['owner_name']}** · Requested: {req['created_at'][:10]}")
                    with h2:
                        st.markdown(f"<div style='text-align:right;'>{render_status_badge(req['status'], req['payment_status'])}</div>", unsafe_allow_html=True)

                    if req["status"] == STATUS_RETURNED:
                        refund_val = req.get("refund_amount") if isinstance(req, dict) else req["refund_amount"]
                        refunded_time = req.get("refunded_at") if isinstance(req, dict) else req["refunded_at"]
                        if refund_val is not None and refund_val > 0:
                            st.success(f"💰 Demo refund of **{format_rupees(refund_val)}** recorded on {str(refunded_time)[:16] if refunded_time else 'return'}.")
                        else:
                            st.info("Item returned and loan closed.")
                    elif req["status"] == STATUS_REJECTED:
                        st.caption("Request was rejected by the owner.")
                    elif req["status"] == STATUS_CANCELLED:
                        st.caption("You cancelled this request.")


# ---------------------------------------------------------
# Primary Section D: Requests (Owner View)
# ---------------------------------------------------------
def show_requests():
    student = logged_in_student()
    st.title("Incoming Requests & Lending")
    st.caption("Manage requests for items you own, verify borrower demo payments, and confirm safe returns.")

    owner_requests = load_borrowing_requests(student["id"], as_owner=True)

    if not owner_requests:
        with st.container(border=True):
            st.markdown("#### No requests received yet")
            st.caption("When other students request to borrow your listings, their requests will appear here.")
            st.button("List Another Item", key="req_empty_list_btn", on_click=navigate_to, args=("List an Item",))
        return

    pending_tab, active_tab, history_tab = st.tabs([
        "Pending Decisions",
        "Active Loans & Returns",
        "Lending History",
    ])

    with pending_tab:
        pending_reqs = [r for r in owner_requests if r["status"] == STATUS_PENDING]
        if not pending_reqs:
            st.info("No pending requests awaiting your decision.")
        else:
            for req in pending_reqs:
                with st.container(border=True):
                    h1, h2 = st.columns([3, 1])
                    with h1:
                        st.markdown(f"### {req['item_name']}")
                        st.caption(f"Borrower: **{req['borrower_name']}** ({req['borrower_email']}) · Requested on {req['created_at'][:16]}")
                    with h2:
                        st.markdown(f"<div style='text-align:right;'>{render_status_badge(req['status'])}</div>", unsafe_allow_html=True)

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Duration", f"{req['requested_days']} days")
                    with c2:
                        st.metric("Borrowing Fee", format_rupees(req["borrowing_fee"]))
                    with c3:
                        st.metric("Refundable Deposit", format_rupees(req["refundable_deposit"]))

                    st.markdown("<hr style='margin: 0.8rem 0;'>", unsafe_allow_html=True)
                    b1, b2, _ = st.columns([1, 1, 2])
                    with b1:
                        if st.button("Accept Request", key=f"owner_acc_{req['id']}"):
                            accept_borrowing_request(req["id"])
                            st.rerun()
                    with b2:
                        if st.button("Reject Request", key=f"owner_rej_{req['id']}"):
                            reject_borrowing_request(req["id"])
                            st.rerun()

    with active_tab:
        active_reqs = [r for r in owner_requests if r["status"] == STATUS_ACCEPTED]
        if not active_reqs:
            st.info("No active loans at this time.")
        else:
            for req in active_reqs:
                with st.container(border=True):
                    h1, h2 = st.columns([3, 1])
                    with h1:
                        st.markdown(f"### {req['item_name']}")
                        st.caption(f"Borrower: **{req['borrower_name']}** ({req['borrower_email']})")
                    with h2:
                        st.markdown(f"<div style='text-align:right;'>{render_status_badge(req['status'], req['payment_status'], req['return_condition'])}</div>", unsafe_allow_html=True)

                    m1, m2, m3 = st.columns(3)
                    with m1:
                        st.metric("Duration", f"{req['requested_days']} days")
                    with m2:
                        st.metric("Borrowing Fee", format_rupees(req["borrowing_fee"]))
                    with m3:
                        st.metric("Security Deposit", format_rupees(req["refundable_deposit"]))

                    if req["payment_status"] == PAYMENT_UNPAID:
                        st.warning("⏳ **Awaiting Borrower Payment:** You accepted this request. Borrower must review terms and complete demo payment before item handover.")
                        if st.button("Cancel Acceptance", key=f"owner_cancel_unpaid_{req['id']}"):
                            cancel_borrowing_request(req["id"])
                            st.rerun()
                    else:
                        total_paid_val = req.get("total_paid") if isinstance(req, dict) else req["total_paid"]
                        st.success(f"💳 **Payment Confirmed:** Borrower paid {format_rupees(total_paid_val or (req['borrowing_fee'] + req['refundable_deposit']))} via Demo Payment.")

                        # Overdue check
                        overdue_days, late_fee = calculate_late_fee(
                            req["fee_type"], req["fee_amount"], req["requested_days"],
                            req["paid_at"], req["refundable_deposit"]
                        )
                        if overdue_days > 0:
                            st.error(f"⚠️ **Item Overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}:** Accrued late fee: **{format_rupees(late_fee)}**.")

                        has_ret_req = bool(req.get("return_requested_at") if isinstance(req, dict) else req["return_requested_at"])
                        if has_ret_req:
                            st.info(f"📦 Borrower marked item as returned on {str(req['return_requested_at'])[:16]}. Please inspect the item.")

                        # Return inspection actions
                        if req["return_condition"] == RETURN_DISPUTED:
                            st.error(f"⚠️ **Borrower Disputed Damage:** '{req['dispute_reason']}'.")
                            if st.button("🤝 Resolve Dispute", key=f"res_btn_{req['id']}"):
                                show_resolve_dispute_dialog(req["id"])
                        elif req["return_condition"] == RETURN_DAMAGE:
                            st.warning(f"Damage claim pending borrower response: {req['damage_notes']} (Deduction: {format_rupees(req['damage_deduction'])})")
                        else:
                            st.markdown("<hr style='margin: 0.8rem 0;'>", unsafe_allow_html=True)
                            r1, r2, r3 = st.columns([1.5, 1.5, 1.5])
                            with r1:
                                if st.button("✅ Confirm Safe Return", key=f"safe_ret_{req['id']}"):
                                    confirm_safe_return(req["id"])
                                    st.rerun()
                            with r2:
                                if st.button("⚠️ Report Damage / Deduction", key=f"dmg_btn_{req['id']}"):
                                    show_damage_dialog(req["id"])
                            with r3:
                                if st.button("Cancel Loan & Refund", key=f"owner_cancel_paid_{req['id']}"):
                                    cancel_borrowing_request(req["id"])
                                    st.rerun()

    with history_tab:
        history_reqs = [
            r for r in owner_requests
            if r["status"] in (STATUS_RETURNED, STATUS_REJECTED, STATUS_CANCELLED)
        ]
        if not history_reqs:
            st.info("No past lending history.")
        else:
            for req in history_reqs:
                with st.container(border=True):
                    h1, h2 = st.columns([3, 1])
                    with h1:
                        st.markdown(f"#### {req['item_name']}")
                        st.caption(f"Borrower: **{req['borrower_name']}** · Requested: {req['created_at'][:10]}")
                    with h2:
                        st.markdown(f"<div style='text-align:right;'>{render_status_badge(req['status'], req['payment_status'])}</div>", unsafe_allow_html=True)

                    if req["status"] == STATUS_RETURNED:
                        refund_val = req.get("refund_amount") if isinstance(req, dict) else req["refund_amount"]
                        if not refund_val:
                            refund_val = req["refundable_deposit"]
                        st.success(f"Item returned safely. Demo deposit refund of {format_rupees(refund_val)} processed.")
                    elif req["status"] == STATUS_REJECTED:
                        st.caption("You rejected this request.")
                    elif req["status"] == STATUS_CANCELLED:
                        st.caption("Borrower cancelled before approval.")


# ---------------------------------------------------------
# Sidebar Navigation & Main App Layout
# ---------------------------------------------------------
def show_main_app():
    student = logged_in_student()
    metrics = load_student_metrics(student["id"])

    # Compact sidebar account box
    with st.sidebar:
        st.markdown("### 🎒 ShareSphere")
        st.caption("Campus Peer-to-Peer Sharing")

        st.markdown(
            f"""
            <div class="user-profile-box">
                <div style="font-weight: 700; color: #F8FAFC; font-size: 0.95rem;">👤 {student['name']}</div>
                <div style="color: #94A3B8; font-size: 0.8rem; margin-bottom: 8px;">{student['email']}</div>
                <div style="font-size: 0.78rem; color: #5EEAD4; font-weight: 600;">
                    📦 {metrics['items_listed']} Listed &nbsp;·&nbsp;
                    🎒 {metrics['borrowing_active']} Active &nbsp;·&nbsp;
                    📩 {metrics['requests_received']} Requests
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.button("Log Out", key="sidebar_logout_btn", on_click=logout_student)
        st.markdown("<hr style='margin: 0.8rem 0;'>", unsafe_allow_html=True)

        # Exactly 4 primary navigation options
        page = st.radio(
            "Navigation",
            PAGES,
            index=PAGES.index(st.session_state.nav_page) if st.session_state.nav_page in PAGES else 0,
            key="nav_page_selector",
        )

    # Sync navigation state
    if page != st.session_state.get("nav_page"):
        st.session_state.nav_page = page
        st.session_state.list_errors = []

    # Route to exactly one of the four primary sections
    if st.session_state.nav_page == "Browse Items":
        show_browse_items()
    elif st.session_state.nav_page == "List an Item":
        show_list_an_item()
    elif st.session_state.nav_page == "My Borrowings":
        show_my_borrowings()
    elif st.session_state.nav_page == "Requests":
        show_requests()


# ---------------------------------------------------------
# Application Initialization & Entry Point
# ---------------------------------------------------------
init_database()
init_session()

if is_logged_in():
    show_main_app()
else:
    show_auth_pages()
