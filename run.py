from src import create_app

app, celery = create_app()
app.app_context().push()

from src.main import *

if __name__ == '__main__':
    app.run()
