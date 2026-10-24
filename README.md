# 🎒 ShareSphere — Campus Item Sharing Platform

### Share More. Spend Less. Build a Connected Campus.

🌐 **Live Demo:** [Launch ShareSphere](https://sharesphere-pdma8pnqkapmbptpskvmys.streamlit.app/)

💻 **GitHub Repository:** [ShareSphere](https://github.com/Grandhisahasra123/ShareSphere)

---

## 📌 Overview

ShareSphere is a campus-focused peer-to-peer item sharing and borrowing platform that allows students to list, discover, lend, and borrow items within their college community.

The platform provides student authentication, item management, borrowing requests, return tracking, and simulated security-deposit and refund handling.

Built with Python and Streamlit, ShareSphere uses Supabase PostgreSQL for cloud data storage and SQLite for local development.

## ❗ Problem Statement

Students often need items such as textbooks, calculators, and lab accessories for short periods. Purchasing these items for occasional use increases expenses and leaves useful resources underutilized.

Informal borrowing arrangements can also make it difficult to track item availability, requests, returns, deposits, and disputes.

ShareSphere addresses these challenges through a centralized platform that makes campus item sharing more organized and accessible.

## 💡 Proposed Solution

ShareSphere connects students who have items to lend with students who need them temporarily.

Students can register, list items, discover available resources, submit borrowing requests, manage approvals, and track returns through a structured workflow.

The platform aims to reduce unnecessary purchases, improve resource utilization, and encourage a sharing culture within campus communities.

## ✨ Key Features

### 🔐 Student Authentication
- Student registration and login.
- Campus email-domain validation.
- Scrypt-based password hashing.
- Database-backed account management.

### 📦 Item Management
- Create and manage item listings.
- Browse, search, and filter available items.
- Associate items with their owners.
- Display borrowing fees and security deposits where supported.

### 🔄 Borrowing Workflow
- Submit borrowing requests.
- Accept or reject requests.
- Track request statuses.
- Manage item returns.
- Database safeguards for important borrowing operations.

### 💰 Deposit and Refund Simulation
- Maintain simulated payment and deposit records.
- Track return-related deposit outcomes.
- Support damage reporting and dispute handling where implemented.

**Note:** Payments and refunds are simulated. Real-money transactions and payment-gateway integration are planned enhancements.

### 🗄️ Hybrid Database Support
- Supabase PostgreSQL for cloud deployment.
- SQLite for local development and fallback operation.
- Environment-based database configuration.
- Existing-data migration support.
- Relational constraints and indexes for data integrity.

## 🔁 Application Workflow

```text
Student Registration / Login
             |
             v
     Browse or List Items
             |
             v
   Submit Borrowing Request
             |
             v
 Owner Accepts or Rejects
             |
             v
   Borrowing Status Tracking
             |
             v
       Return the Item
             |
             v
 Update Return and Demo
     Deposit Records
```
### 🏗️ System Architecture

```text
+------------------------------+
|           Students           |
+--------------+---------------+
               |
               v
+------------------------------+
|     Streamlit Application    |
|                              |
|  Authentication              |
|  Item Management              |
|  Borrowing Workflow           |
|  Deposit Simulation           |
+--------------+---------------+
               |
               v
+------------------------------+
|       Database Backend       |
|                              |
|  PostgreSQL / Supabase       |
|  SQLite for Local Development|
+------------------------------+

```
## 🛠️ Technology Stack

| Technology | Purpose |
|------------|---------|
| Python | Core application logic |
| Streamlit | User interface and web application |
| PostgreSQL | Cloud database |
| Supabase | Managed PostgreSQL database hosting |
| SQLite | Local development database |
| Psycopg 3 | PostgreSQL database connectivity |
| python-dotenv | Loading environment variables |
| Streamlit Community Cloud | Application deployment |
| Git & GitHub | Version control and source code management |

---

## 🗃️ Database Design

ShareSphere uses a relational database to manage users, items, borrowing requests, and deposit-related records.

### Main Database Tables

| Table | Description |
|-------|-------------|
| `students` | Stores registered student information and authentication details |
| `items` | Stores item listings, availability, ownership, and related details |
| `borrowing_requests` | Tracks borrowing requests and their statuses |
| `demo_payments` | Stores simulated deposit and refund-related records |

The database uses relational constraints to help maintain data consistency and integrity.

---

## 🔒 Security and Data Handling

- **Password Security:** Student passwords are stored using scrypt hashing rather than plain text.
- **Database Configuration:** Database connection details are configured through environment variables or Streamlit Secrets.
- **Data Integrity:** Database constraints help maintain consistent records.
- **Sensitive Files:** Local environment files and database files should not be committed to the public repository.
- **Campus Email Validation:** Registration includes campus email-domain validation. This alone does not verify a student's identity.
- **Payment Simulation:** Deposit and refund records are simulated. The application does not process real financial transactions.

Additional security testing and improvements would be required before production use.

---

## 🚀 Getting Started

Follow these steps to run ShareSphere on your local machine.

### Prerequisites

Make sure you have installed:

- Python 3.10 or a compatible version
- Git
- A Supabase project if you want to use the cloud PostgreSQL database

### 1. Clone the Repository

```bash
git clone https://github.com/Grandhisahasra123/ShareSphere.git
cd ShareSphere
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate the environment on Windows:

```bash
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project directory and configure your database connection.

```env
DATABASE_URL=your_actual_database_connection_string
```

Replace the placeholder with your actual PostgreSQL connection string.

**Important:** Never upload your `.env` file or expose your database credentials publicly.

### 5. Run the Application

```bash
streamlit run app.py
```

The application will open in your browser.

---

## ☁️ Deployment

ShareSphere is deployed using **Streamlit Community Cloud** with Supabase PostgreSQL as its cloud database.

- **Live Application:** [Launch ShareSphere](https://sharesphere-pdma8pnqkapmbptpskvmys.streamlit.app/)
- **GitHub Repository:** [Grandhisahasra123/ShareSphere](https://github.com/Grandhisahasra123/ShareSphere)
- **Deployment Platform:** Streamlit Community Cloud
- **Database:** Supabase PostgreSQL

The database connection string should be configured securely through the application's Streamlit Secrets settings.

---

## 📁 Project Structure

```text
ShareSphere/
│
├── app.py              # Main Streamlit application
├── db_backend.py       # Database connectivity and operations
├── requirements.txt    # Python dependencies
├── README.md           # Project documentation
├── .gitignore          # Files excluded from Git
└── .env                # Local environment variables (not committed)
```

---

## 🔮 Future Enhancements

The following features could be added to improve ShareSphere:

- **Item Image Uploads:** Allow students to upload photos of items they want to lend.
- **Real Payment Integration:** Integrate a secure payment gateway for deposits and refunds.
- **Email Verification:** Strengthen account verification.
- **Notifications:** Notify users about borrowing requests, approvals, and returns.
- **Due-Date Reminders:** Send reminders before items are due.
- **Ratings and Reviews:** Allow users to review borrowing and lending experiences.
- **Enhanced Dispute Management:** Improve the process for reporting and resolving item-related disputes.
- **Analytics Dashboard:** Display platform usage and borrowing statistics.
- **Mobile-Friendly Experience:** Improve usability across mobile devices.

These are planned enhancements and are not necessarily part of the current implementation.

---

## 🤝 Contributing

Contributions and suggestions are welcome!

1. Fork the repository.
2. Create a new branch for your changes.
3. Make your changes and test them.
4. Commit and push your changes.
5. Open a pull request.

---
