
# ───────────────────────── helpers ───────────────────────── #
# backend/services/user_onboard.py
from routes.devices.common import request, jsonify, datetime, timedelta, Blueprint, random, string, requests, timezone
from config import TRACCAR_API_URL, HEADERS_JSON, HEADERS_FORM
import re
import secrets


def _rand_pwd(n=10):
    return secrets.token_urlsafe(24)

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
        "administrator": False,
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
    r = requests.post(TRACCAR_API_URL + "users", json=payload, headers=HEADERS_JSON, timeout=15, allow_redirects=False)

    if r.status_code == 400 and "Duplicate entry" in r.text:
        print(f"User with email {email} already exists")    
        raise ValueError("User with this email already exists")
    r.raise_for_status() 
    return r.json()["id"], pwd

def _login_get_cookie(email, pwd) -> str:
    payload = {"email": email, "password": pwd}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    resp = requests.post(TRACCAR_API_URL + "session", data=payload, headers=headers, timeout=15, allow_redirects=False)
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
                          json=_notification_wizard(nt), headers=headers, timeout=15, allow_redirects=False)
        r.raise_for_status()
        nid = r.json()["id"]; created.append(nid)
    return created

def _trigger_pwd_reset(email):
    requests.post(TRACCAR_API_URL+"password/reset",
                  data={"email": email}, headers=HEADERS_FORM, timeout=15, allow_redirects=False).raise_for_status()





# ───────────────────────── public service ───────────────────────── #

def onboard_user(payload: dict):
    if not isinstance(payload, dict):
        return {"error": "Customer details are required."}, 400
    name, email, phone = (payload.get(key) for key in ("name", "email", "phone"))
    if (not isinstance(name, str) or not name.strip() or len(name) > 200
            or not isinstance(email, str) or len(email) > 254
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip())
            or not isinstance(phone, str) or len(phone) > 40):
        return {"error": "Provide a customer name, valid email and phone field."}, 400
    name, email = name.strip(), email.strip()
    try:
        user_id, temp_pwd = _create_user(name, email, phone)
    except ValueError:
        return {"error": "User with this email already exists or could not be created."}, 400
    except requests.RequestException:
        return {"error": "Could not create the customer account."}, 502
    user_cookie = None
    try:
        user_cookie = _login_get_cookie(email, temp_pwd)
        _create_notifications(user_cookie)
        _trigger_pwd_reset(email)
    except (requests.RequestException, ValueError, KeyError, RuntimeError):
        return {"error": "Customer created, but setup could not be completed. Check the account before retrying."}, 502
    finally:
        if user_cookie:
            try:
                requests.delete(TRACCAR_API_URL + "session", cookies={"JSESSIONID": user_cookie}, timeout=5, allow_redirects=False)
            except requests.RequestException:
                pass
    return {"user_id": user_id, "user_name": name, "user_email": email}, 201
