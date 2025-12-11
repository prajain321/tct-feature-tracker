import time

import schedule

from packages.database.schema import Database
from packages.balancer import force_refetch_and_update
from common import get_rocm_unique_value

db = Database('7.2')


def job():
    """Execute scheduled job to refetch and update all collections."""
    arr = db.get_all_collections()
    print("Refetching and updating all collections...")
    for i in arr:
        force_refetch_and_update(
            rocm_version=i, unique_key=str(get_rocm_unique_value(i)))


# Run every second
schedule.every(30).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(1)
