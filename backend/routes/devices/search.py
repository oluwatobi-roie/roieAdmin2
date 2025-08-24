from .common import request, jsonify, datetime, timezone, db, text, exclude_users_list
from routes.devices import device_bp
from services.login_required import login_required

# /api/device/search
@device_bp.route('/search', methods=['GET'])
@login_required
def search_device_or_user():
    search = request.args.get('term')
    if not search:
        return jsonify({"error": "Missing search parameter"}), 400

    # ─────────────────────────────────────────────────────────────────────────
    #  A.  SEARCH BY USER E‑MAIL  →  return USER PROFILE  (+ all their devices)
    # ─────────────────────────────────────────────────────────────────────────
    if '@' in search:
        # 1. find the user
        user_row = db.session.execute(text("""
            SELECT id, name, email, phone, expirationtime, disabled
            FROM tc_users
            WHERE email LIKE :email
            LIMIT 1
        """), {"email": search}).fetchone()

        if not user_row:
            return jsonify({"error": "User not found"}), 404
        if user_row.id in exclude_users_list: # Exclude certain users such as admin or Noc Service account owners
            return jsonify({"error": "User is an Admin"}), 403

        # 2. collect device IDs (direct + group)
        device_ids = set()

        # direct
        direct_ids = db.session.execute(text("""
            SELECT deviceid FROM tc_user_device WHERE userid = :uid
        """), {"uid": user_row.id}).scalars().all()
        device_ids.update(direct_ids)

        # via groups
        group_ids = db.session.execute(text("""
            SELECT groupid FROM tc_user_group WHERE userid = :uid
        """), {"uid": user_row.id}).scalars().all()

        if group_ids:
            group_devices = db.session.execute(text("""
                SELECT id FROM tc_devices WHERE groupid IN :gids
            """), {"gids": tuple(group_ids)}).scalars().all()
            device_ids.update(group_devices)

        if not device_ids:
            return jsonify({
                "user": _format_user(user_row),
                "devices": []
            })

        # 3. fetch up‑to‑10 device profiles (reuse your existing formatter)
        devices_sql = text("""
            SELECT 
              d.id            AS device_id,
              d.name          AS device_name,
              d.uniqueid      AS imei,
              d.phone         AS device_phone,
              d.status        AS device_status,
              d.model,
              d.groupid,
              d.positionid,
              p.fixtime,
              p.devicetime,
              p.address,
              g.name          AS group_name
            FROM tc_devices d
            LEFT JOIN tc_positions p ON p.id = d.positionid
            LEFT JOIN tc_groups    g ON g.id = d.groupid
            WHERE d.id IN :dids
        """)
        device_rows = db.session.execute(devices_sql, {"dids": tuple(device_ids)}).fetchall()

        device_profiles = [_build_device_profile(dev) for dev in device_rows]

        return jsonify({
            "user": _format_user(user_row),
            "devices": device_profiles,
            "truncated": len(device_ids) > 10
        })

    # ─────────────────────────────────────────────────────────────────────────
    #  B.  DEVICE SEARCH  →  return list of DEVICE PROFILES
    # ─────────────────────────────────────────────────────────────────────────
    device_sql = text("""
        SELECT 
          d.id            AS device_id,
          d.name          AS device_name,
          d.uniqueid      AS imei,
          d.phone         AS device_phone,
          d.status        AS device_status,
          d.model,
          d.groupid,
          d.positionid,
          p.fixtime,
          p.devicetime,
          p.address,
          g.name          AS group_name
        FROM tc_devices d
        LEFT JOIN tc_positions p ON p.id = d.positionid
        LEFT JOIN tc_groups    g ON g.id = d.groupid
        WHERE 
              CAST(d.id AS CHAR) = :search
          OR  d.uniqueid         = :search
          OR  d.phone       LIKE :phone
          OR  d.name        LIKE :name
    """)
    device_rows = db.session.execute(device_sql, {
        "search": search,
        "name":   f"%{search}%",
        "phone":  f"%{search}%"
    }).fetchall()

    if not device_rows:
        return jsonify({"error": "Device not found"}), 404

    device_profiles = [_build_device_profile(row) for row in device_rows]
    return jsonify(device_profiles)


# ───────────────────────── helper formatters ───────────────────────── #

def _format_user(row):
    return {
        "name":  row.name,
        "email": mask_email(row.email),
        "phone": mask_phone(row.phone),
        "expiry": row.expirationtime.isoformat() if row.expirationtime else None,
        "status": get_account_status(row.expirationtime, row.disabled)
    }

def _build_device_profile(device):
    # fetch users linked to this device (same logic you already had)
    # (left out here for brevity, reuse exact code you wrote earlier)
    user_profiles = _fetch_users_for_device(device.device_id, device.groupid)

    return {
        "device_id":        device.device_id,
        "device_name":      device.device_name,
        "imei":             device.imei,
        "phone":            device.device_phone,
        "model":            device.model,
        "group":            device.group_name,
        "position_address": device.address,
        "last_fix_time":    device.fixtime,
        "last_device_time": device.devicetime,
        "online_status":    get_online_status(device.fixtime,
                                              device.devicetime,
                                              device.device_status),
        "user_profiles":    user_profiles
    }

def _fetch_users_for_device(device_id, group_id=None):
    if group_id:
        user_sql = text("""
            SELECT DISTINCT u.id, u.name, u.email, u.phone, u.expirationtime, u.disabled
            FROM tc_users u
            WHERE u.id IN (
                SELECT ud.userid FROM tc_user_device ud WHERE ud.deviceid = :device_id
                UNION
                SELECT ug.userid FROM tc_user_group ug WHERE ug.groupid = :group_id
            )
        """)
        user_rows = db.session.execute(user_sql, {
            "device_id": device_id,
            "group_id": group_id
        }).fetchall()
    else:
        user_sql = text("""
            SELECT DISTINCT u.id, u.name, u.email, u.phone, u.expirationtime, u.disabled
            FROM tc_users u
            WHERE u.id IN (
                SELECT ud.userid FROM tc_user_device ud WHERE ud.deviceid = :device_id
            )
        """)
        user_rows = db.session.execute(user_sql, {
            "device_id": device_id
        }).fetchall()

    user_profiles = []
    for row in user_rows:
        if row.id in exclude_users_list:
            continue
        user_profiles.append({
            "name": row.name,
            "email": mask_email(row.email),
            "phone": mask_phone(row.phone),
            "expiry": row.expirationtime.isoformat() if row.expirationtime else None,
            "status": get_account_status(row.expirationtime, row.disabled)
        })

    return user_profiles


# --- Utility Functions --- #

def mask_email(email):
    if not email or '@' not in email:
        return "****"
    name, domain = email.split('@')
    return name[0] + '***********' + name[-2:] + '@' + domain

def mask_phone(phone):
    if not phone or len(phone) < 5:
        return "***"
    return phone[:3] + '****' + phone[-2:]

def get_account_status(expiry, disabled):
    if disabled == 1:
        return "Disabled"
    if expiry and expiry < datetime.utcnow():
        return "Expired"
    return "Active"


def _to_aware_utc(dt):
    """
    Ensure a datetime is timezone‑aware in UTC.
    Assumes DB datetimes are already recorded in UTC but naive.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:                  # naive → attach UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)      # already aware → convert to UTC


def get_online_status(fix_time, device_time, device_status):
    """
    Return dict {"status": "...", "recommendation": "..."} 
    according to NOC rules.
    """
    try:
        fix_time    = _to_aware_utc(fix_time)
        device_time = _to_aware_utc(device_time)
        now         = datetime.now(timezone.utc)

        # if any critical field missing
        if not fix_time or not device_time or not device_status:
            return {"status": "Unknown", "recommendation": "Data incomplete"}

        minutes_since_fix    = (now - fix_time).total_seconds() / 60
        minutes_since_device = (now - device_time).total_seconds() / 60
        status_lower         = device_status.lower()

        # ── NOC Passed Online ───────────────────────────────────────────
        if (
            minutes_since_device <= 30 and
            minutes_since_fix   <= 40 and
            status_lower == "online"
        ):
            return {"status": "NOC Passed Online", "recommendation": "None"}

        # ── NOC Failed Online (case 1) ──────────────────────────────────
        if (
            minutes_since_device <= 20 and
            minutes_since_fix   >  90 and
            status_lower == "online"
        ):
            return {"status": "NOC Failed Online",
                    "recommendation": "Recharge Device"}

        # ── NOC Failed Online (case 2) ──────────────────────────────────
        if (
            minutes_since_device > 20 and
            status_lower == "online"
        ):
            return {"status": "NOC Failed Online",
                    "recommendation": "Recharge Device"}

        # ── Offline ────────────────────────────────────────────────────
        if (
            minutes_since_device > 40 and
            status_lower in ("offline", "unknown")
        ):
            return {"status": "Device is Offline",
                    "recommendation": ("Check back in few hours / Confirm if "
                                       "vehicle is under maintenance / Schedule "
                                       "for Maintenance")}

        # ── Default fallback ────────────────────────────────────────────
        return {"status": "Likely Online, but not updating frequently",
                "recommendation": "Monitor for changes"}

    except Exception as e:
        return {"status": "Unknown",
                "recommendation": f"Error occurred: {e}"}




