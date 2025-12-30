# OdooApi Project

## Description
This project is a Django-based API integration with Odoo.

## Setup

1.  **Clone the repository**
2.  **Create a virtual environment**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
3.  **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configuration**
    - Create a `.env` file in the root directory (see `.env.example` or ask the administrator).
    - Ensure `SECRET_KEY` and other sensitive variables are set.
5.  **Run Migrations**
    ```bash
    python manage.py migrate
    ```
6.  **Run Server**
    ```bash
    python manage.py runserver
    ```
