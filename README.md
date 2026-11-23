# Django: регистрация, вход с капчей, личный кабинет

## Команды (терминал VS Code, Ctrl+`)
python -m venv venv
venv\Scripts\activate            # Windows (PowerShell/cmd)
pip install -r requirements.txt
python manage.py migrate
python manage.py test accounts -v 2        # только тесты
python manage.py test_report               # тесты + Word-отчёт -> reports/test_report.docx
python manage.py runserver                 # http://127.0.0.1:8000/
