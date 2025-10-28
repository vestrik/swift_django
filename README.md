Celery:
celery -A swift_django worker --loglevel=info 

Flower:
celery -A swift_django flower --port=5555 --basic-auth="admin:password" --persistent=True --db="flower_db" --state_save_interval=18000


Для mysql
sudo apt-get install pkg-config python3-dev default-libmysqlclient-dev build-essential

Для генерации пдф
sudo apt-get install libpangocairo-1.0-0