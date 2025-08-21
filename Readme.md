Roie Web Application

Roie Technologies' modern web platform for technical support, asset monitoring, user/device management, NOC subscription, and financial audit.

🔧 Tech Stack

Frontend: React.js (with TypeScript optionally)

Backend: Flask (Python)

Database: SQL (Connected to Traccar)

Deployment: Mobile & Desktop Web

🎯 Core Features

✅ Version 1.0

1. Technical Support Query Tool

Search asset by IMEI, device name, username, or email.

Display device profile:

Device Name

Device Phone Number

Device Phone Number Group (from SIM DB or fallback to Unknown-[carrier])

Make/Model of Vehicle

Device IMEI

Online Status Insight (based on Last Fix, Device, and Server Time)

Distance Travelled (3-day km sum from reports)

Ignition Cycle Count (report-based)

Engine Block Status

Device Group (excluding certain groups)

User(s) managing device (excluding certain user IDs), with obfuscated contact details

Name

Email (first char + last 4 chars visible, rest hashed)

Phone Number (first 3 + last 2 digits visible, rest hashed)

Expiry Date

Account Status: Active / Expired / Disabled

2. Add New User

Form for creating a new user and linking to device or group.

3. Add New Device

Identify available device IDs (skipping 1-10).

Suggest next available slot from deleted records.

Add new device with required attributes.

🚧 Version 3.0 (Planned)

4. Financial Audit

Admin receives money from HQ.

Disbursement tracking and reporting.

🚧 Version 4.0 (Planned)

5. NOC Subscribers

Subscribe a group to Roie NOC services.

Monitor for:

Parked outside geofence > 30 minutes

Offline outside geofence > 10 minutes

💡 Design Notes

Responsive UI (Mobile + Desktop)

Friendly UX with clean typography and intuitive color grading

Modular frontend for feature expansion

🚀 Getting Started

Prerequisites

Python 3.10+

Node.js 18+

SQL DB running (Traccar-compatible)

Setup Instructions

# Clone the repo
$ git clone https://github.com/your-username/roie-webapp.git
$ cd roie-webapp

# Backend Setup
$ cd backend
$ python3 -m venv venv && source venv/bin/activate
$ pip install -r requirements.txt
$ flask run

# Frontend Setup
$ cd frontend
$ npm install
$ npm run dev

📁 Project Structure

roie-webapp/
├── backend/
│   ├── app.py
│   ├── routes/
│   └── models/
├── frontend/
│   ├── src/
│   ├── components/
│   ├── pages/
│   └── App.jsx
├── README.md
└── .env

🔒 Security Notes

Sensitive data like emails/phone numbers are hashed appropriately.

Expiry and account validation handled securely.

👨‍💻 Contribution

Want to contribute?

Fork the repo

Create a feature branch

Submit PR with detailed description

📄 License

MIT License

🌐 Author

Oluwatobi AkomolafeLinkedInPowered by Roie Technologies