from celery import Celery
import os, time
app = Celery(
    'tasks',
    broker=  os.environ.get('CELERY_BROKER_URL'),
    backend= os.environ.get('CELERY_RESULT_BACKEND')
)

@app.task
def add(x, y):
    time.sleep(5)
    return x + y