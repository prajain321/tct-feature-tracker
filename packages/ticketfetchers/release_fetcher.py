import requests as rq

def get_releases():
    try:
        response  = rq.get("http://api.rastra-rts.amd.com/releases?issue_type=feature")
        print(response.status_code)
        rocm_releases = response.json()
        releases_labels = [i["value"] for i in rocm_releases]
        return releases_labels
    except rq.exceptions.RequestException as e:
        return {"error": str(e)}
    
get_releases()