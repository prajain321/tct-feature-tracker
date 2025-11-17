import schedule
import time
from packages.database.schema import Database
from packages.balancer import force_refetch_and_update
from common import get_rocm_unique_value

db = Database('7.2')
def job():
    arr = db.get_all_collections()
    for i in arr:
        force_refetch_and_update(rocm_version=i, unique_key=str(get_rocm_unique_value(i)))

# Run every 10 minutes
schedule.every(30).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(1)