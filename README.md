# Flit Backend API

## 📋 Overview

Flit is a modern recruitment and job application platform that connects job seekers with employers. This repository contains the backend API built with Django REST Framework, providing a robust and scalable foundation for the Flit platform.

## 🚀 Features

- **User Authentication & Authorization** (JWT-based)
- **Job Posting & Management**
- **Application Tracking System (ATS)**
- **Real-time Chat** using WebSockets
- **Video Interview Platform**
- **Resume Parsing & Management**
- **Company Profiles & Employer Dashboards**
- **Project Showcase for Candidates**
- **Stories/Portfolio Features**

## 🛠️ Tech Stack

- **Backend Framework**: Django 5.2
- **REST API**: Django REST Framework
- **Database**: PostgreSQL
- **Authentication**: JWT (JSON Web Tokens)
- **Real-time Features**: Django Channels
- **File Storage**: AWS S3
- **Containerization**: Docker
- **API Documentation**: Swagger/OpenAPI

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 13+
- Daphne (for WebSockets)
- AWS S3 Bucket (for file storage)
- Google OAuth Credentials (for authentication)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/flit-backend.git
   cd flit-backend
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**
   Create a `.env` file in the project root and add the following variables:
   ```env
   DEBUG=True
   SECRET_KEY=your-secret-key
   DATABASE_URL=postgres://user:password@localhost:5432/flit_db
   AWS_ACCESS_KEY_ID=your-aws-access-key
   AWS_SECRET_ACCESS_KEY=your-aws-secret-key
   AWS_STORAGE_BUCKET_NAME=your-s3-bucket
   GOOGLE_OAUTH2_CLIENT_ID=your-google-client-id
   GOOGLE_OAUTH2_CLIENT_SECRET=your-google-client-secret
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server**
   ```bash
   python manage.py runserver
   ```

## 🏗️ Project Structure

```
flit_backend/
├── accounts/                # User authentication and profiles
├── applications/            # Job applications management
├── candidates/              # Candidate profiles and resumes
├── chat/                    # Real-time messaging
├── companies/               # Company profiles
├── employers/               # Employer dashboards
├── jobs/                    # Job postings
├── projects/                # Project showcases
├── stories/                 # Candidate/company stories
├── utils/                   # Utility functions
├── flit_backend/            # Project settings
├── manage.py                # Django management script
└── requirements.txt         # Project dependencies
```



## 🐳 Docker Setup

1. Build and run the containers:
   ```bash
   docker-compose up --build
   ```

2. Run migrations:
   ```bash
   docker-compose exec web python manage.py migrate
   ```

3. Create superuser:
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

## 🧪 Testing

To run tests:
```bash
python manage.py test
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -ws://127.0.0.1:8000/ws/chat/1/2/b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request
