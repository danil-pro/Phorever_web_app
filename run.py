from src import create_app

app, celery = create_app()
app.app_context().push()

# with app.app_context():
from src.main import user_photos

if __name__ == '__main__':
    app.run()
