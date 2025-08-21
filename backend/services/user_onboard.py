
# ───────────────────────── helpers ───────────────────────── #
# backend/services/user_onboard.py
from routes.devices.common import request, jsonify, datetime, timedelta, Blueprint, random, string, requests, timezone
from config import TRACCAR_API_URL, HEADERS_JSON, HEADERS_FORM


def _rand_pwd(n=10):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))

def _notification_wizard(ntype: str) -> dict:
    basic = ['ignitionOn', 'ignitionOff', 'geofenceEnter', 'geofenceExit']
    if ntype in basic:
        return {"always": True, "type": ntype, "notificators": "traccar,web"}
    return {  # alarm
        "attributes": {"alarms": "powerCut"},
        "always": True,
        "type": "alarm",
        "notificators": "traccar,web,mail"
    }

def _create_user(name, email, phone) -> tuple[int, str]:
    pwd = _rand_pwd()
    expiry = (datetime.now(timezone.utc) + timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%SZ')
    payload = {
        "name": name, 
        "email": email, 
        "phone": phone,
        "password": pwd, 
        "fixedEmail": True, 
        "deviceReadonly": True,
        "expirationTime": expiry,
        "attributes": {
            "mapLiveRoutes":"selected","mapFollow":"true","deviceSecondary":"phone",
            "activeMapStyles":",googleRoad,googleSatellite,googleHybrid,custom",
            "positionItems":"speed,address,motion,ignition,fixTime,deviceTime,alarm,blocked"
        }
    }
    r = requests.post(TRACCAR_API_URL + "users", json=payload, headers=HEADERS_JSON)

    if r.status_code == 400 and "Duplicate entry" in r.text:
        print(f"User with email {email} already exists")    
        raise ValueError("User with this email already exists")
    r.raise_for_status() 
    return r.json()["id"], pwd

def _login_get_cookie(email, pwd) -> str:
    payload = {"email": email, "password": pwd}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    resp = requests.post(TRACCAR_API_URL + "session", data=payload, headers=headers)
    resp.raise_for_status()
    cookie = resp.cookies.get("JSESSIONID")

    if not cookie:
        raise RuntimeError("Login succeeded but no JSESSIONID returned")
    return cookie

def _create_notifications(user_cookie) -> list[int]:
    headers = {"Cookie": f"JSESSIONID={user_cookie}", "Content-Type": "application/json"}
    ntypes  = ["ignitionOn","ignitionOff","geofenceEnter","geofenceExit","alarm"]
    created = []
    for nt in ntypes:
        r = requests.post(TRACCAR_API_URL + "notifications",
                          json=_notification_wizard(nt), headers=headers)
        r.raise_for_status()
        nid = r.json()["id"]; created.append(nid)
    return created

def _trigger_pwd_reset(email):
    requests.post(TRACCAR_API_URL+"password/reset",
                  data={"email": email}, headers=HEADERS_FORM).raise_for_status()





# ───────────────────────── public service ───────────────────────── #

def onboard_user(payload: dict):
    try:
        name, email, phone = payload["name"], payload["email"], payload["phone"]
    except KeyError as e:
        return {"error": f"Missing required field: {str(e)}"}, 400

    # 1. create user
    try:
        user_id, temp_pwd = _create_user(name, email, phone)
    except Exception as e:
        return {"error": str(e)}, 400      # ← NO jsonify here!

    # 2. login
    try:
        user_cookie = _login_get_cookie(email, temp_pwd)
    except Exception as e:
        return {"error": f"Login failed: {str(e)}"}, 500

    # 3. notifications
    try:
        _create_notifications(user_cookie)
    except Exception as e:
        return {"error": f"Failed to create notifications: {str(e)}"}, 500

    # 4. trigger reset mail
    try:
        _trigger_pwd_reset(email)
    except Exception as e:
        return {"error": f"Failed to send reset email: {str(e)}"}, 500

    # success
    return {"user_id": user_id,
            "user_name": name,
            "user_email": email}, 201

