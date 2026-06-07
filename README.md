# Capacity Forecaster with Natural Language Querying (IM-02)

## Overview

Capacity Forecaster is an AI-powered capacity planning and forecasting application that helps organizations predict future infrastructure resource utilization and identify potential capacity risks before they occur.

The application allows users to upload historical resource metrics in CSV format and interact with the system using natural language queries such as:

* When will disk utilization reach 80%?
* Will CPU usage exceed 90% within the next 30 days?
* Forecast memory utilization for the next 60 days.
* Show storage growth trends.

The system leverages Google Gemini API for natural language understanding and forecasting techniques such as Linear Regression and ARIMA to generate predictive insights and visualizations.

---

# Problem Statement

Traditional capacity planning often relies on spreadsheets, static reports, and manual analysis. This approach is:

* Time-consuming
* Error-prone
* Difficult to scale
* Reactive instead of proactive

Capacity Forecaster automates infrastructure forecasting by analyzing historical metrics and providing predictive insights through an intelligent natural language interface.

---

# Features

## Authentication & User Management

* User Registration
* User Login
* Secure Logout
* JWT Authentication
* Password Hashing using Bcrypt
* Protected Routes

---

## Dashboard

The dashboard provides a consolidated view of infrastructure health and utilization metrics.

### Dashboard Components

* Capacity Health Score
* Resource Utilization Overview
* CPU Monitoring
* Memory Monitoring
* Disk Monitoring
* KPI Cards
* Interactive Charts
* Dark Mode Support
* Compact Dashboard Layout

---

## Natural Language Query Agent

Users can ask questions in plain English such as:

* When will disk utilization reach 80%?
* Forecast CPU usage for the next 60 days.
* Will memory utilization exceed 90%?
* Show storage growth trends.

### Workflow

1. User submits a natural language query.
2. Gemini API interprets the query.
3. The system identifies:

   * Target metric
   * Forecast horizon
   * Threshold values
   * Forecast intent
4. Appropriate forecasting model is selected.
5. Predictions are generated.
6. Forecast charts and insights are displayed.

---

## Forecasting Engine

### Linear Regression

Used for:

* Trend analysis
* Capacity growth estimation
* Threshold prediction

### ARIMA

Used for:

* Time-series forecasting
* Seasonal pattern detection
* Advanced utilization prediction

### Auto Forecast Mode

Automatically selects the most suitable forecasting model based on historical data characteristics.

---

## CSV Upload

Supports importing infrastructure metrics including:

* CPU Usage
* Memory Usage
* Disk Usage
* Network Traffic
* Active Users
* Response Time
* Error Rate

---

## Forecast History

Users can:

* Save forecast results
* Track query history
* Restore previous forecasts
* View user-specific forecasting records

---

## Notifications & Alerts

The system can generate:

* CPU Threshold Alerts
* Memory Threshold Alerts
* Disk Threshold Alerts
* Capacity Risk Warnings
* Health Score Notifications

---

## Export

Forecast results can be exported as:

* CSV Reports

---

# Technology Stack

## Frontend

* React.js
* Vite
* Recharts
* Axios
* React Router

## Backend

* Python
* FastAPI
* Pandas
* NumPy
* Scikit-Learn
* Statsmodels

## Database

SQLite

Database Location:

```text
data/capacity_forecast.db
```

---

# AI Integration

## Google Gemini API

Google Gemini is used for:

* Natural Language Understanding
* Intent Detection
* Metric Identification
* Threshold Extraction
* Forecast Query Interpretation

### Example

User Query:

```text
When will disk utilization reach 80%?
```

Gemini Interpretation:

```json
{
  "metric": "disk_usage",
  "threshold": 80,
  "intent": "threshold_forecast"
}
```

---

# Forecasting Models

* Linear Regression
* ARIMA
* Auto Forecast Selection

---

# Security

The application incorporates several security mechanisms:

* JWT Authentication
* Bcrypt Password Hashing
* Input Validation
* Protected API Endpoints
* Environment Variable Management
* CORS Protection

---

# Project Structure

```text
FORECASTDATA
│
├── backend
│   ├── .env
│   ├── app.py
│   └── requirements.txt
│
├── data
│   ├── history
│   │   ├── admin_at_example_com.json
│   │   └── user_at_gmail_com.json
│   │
│   ├── capacity_forecast.db
│   └── enhanced_resource_metrics.csv
│
├── frontend
│   ├── src
│   │   ├── components
│   │   ├── hooks
│   │   ├── pages
│   │   ├── services
│   │   ├── App.css
│   │   ├── App.jsx
│   │   └── main.jsx
│   │
│   ├── package.json
│   └── vite.config.js
│
├── .env.example
├── check_db.py
├── README.md
├── start-backend.bat
└── start-frontend.bat
```

---

# Custom React Hooks

## useQueryHistory.js

Responsible for:

* Saving Forecast History
* Loading Previous Forecasts
* Managing Query History
* Restoring Saved Forecast Results

---

## useSettings.js

Responsible for:

* Theme Management
* Alert Threshold Configuration
* User Preferences
* Settings Synchronization

---

# Service Layer

## api.js

Handles communication between frontend and backend.

Responsibilities include:

* Authentication Requests
* CSV Upload
* Forecast Requests
* Metrics Retrieval
* Settings Management

---

# System Architecture

```text
┌─────────────────────────────┐
│      React + Vite UI        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      FastAPI Backend        │
└───────┬───────────┬─────────┘
        │           │
        │           ▼
        │     Google Gemini API
        │
        ▼
 Forecast Engine
(Linear Regression / ARIMA)
        │
        ▼
┌─────────────────────────────┐
│        SQLite Database      │
└─────────────────────────────┘
```

---

# API Endpoints

## Authentication

### Register

```http
POST /auth/register
```

### Login

```http
POST /auth/login
```

### Logout

```http
POST /auth/logout
```

---

## Metrics

### Summary

```http
GET /metrics/summary
```

---

## CSV Upload

```http
POST /upload/csv
```

---

## Forecast Prediction

```http
POST /forecast/predict
```

### Example Request

```json
{
  "question": "When will disk utilization reach 80%?",
  "forecast_days": 60,
  "method": "auto"
}
```

---

# CSV Format

Required Columns:

| Column       | Description            |
| ------------ | ---------------------- |
| date         | Metric Date            |
| cpu_usage    | CPU Utilization (%)    |
| memory_usage | Memory Utilization (%) |
| disk_usage   | Disk Utilization (%)   |

Example:

```csv
date,cpu_usage,memory_usage,disk_usage
2025-01-01,35,50,60
2025-01-02,37,52,61
2025-01-03,39,53,63
```

---

# Demo Credentials

For demonstration purposes only:

```text
Email: admin@example.com
Password: admin123
```

---

# Installation

## Backend Setup

```bash
cd backend

python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

uvicorn app:app --reload
```

Backend URL:

```text
http://localhost:8000
```

---

## Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

---

# Utility Scripts

## check_db.py

Used to:

* Verify SQLite Database Connectivity
* Inspect Database Tables
* Debug Records

---

## start-backend.bat

Starts the FastAPI backend server.

---
## start-frontend.bat
