from src import create_app
from flask_restful import Api

app, celery = create_app()
app.app_context().push()

Api(app)

from src.main import *

if __name__ == '__main__':
    app.run()
