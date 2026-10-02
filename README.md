# Sistema de Facturación Electrónica Ecuador

Proyecto Django 100% web para facturación electrónica en Ecuador.

## Stack
- Django 5.2 LTS
- PostgreSQL
- Redis / Celery
- Django Templates + HTMX/AJAX

## Estado
Base inicial del proyecto. La integración completa de XML, firma XAdES y autorización SRI se implementará por etapas.

## Instalación
```bat
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
