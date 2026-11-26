from .common import request, jsonify, datetime, timezone, db, text, exclude_users_list
from routes.devices import device_bp
from services.login_required import login_required
from sqlalchemy import bindparam

def _escape_like(value):
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


# /api/device/search
@device_bp.route('/search', methods=['GET'])
@login_required
def search_device_or_user():
    search = request.args.get('term', '').strip()
    if len(search) > 254:
        return jsonify(error='Search term is too long'), 400
    user_id = request.args.get('user_id')
    if user_id is not None and (not user_id.isascii() or not user_id.isdigit() or len(user_id) > 19 or not 0 < int(user_id) <= 9223372036854775807):
        return jsonify({'error': 'Invalid customer account ID'}), 400
    if user_id is None and not search:
        return jsonify({"error": "Missing search parameter"}), 400

    # ─────────────────────────────────────────────────────────────────────────
    #  A.  SEARCH BY USER E‑MAIL  →  return USER PROFILE  (+ all their devices)
    # ─────────────────────────────────────────────────────────────────────────
    if user_id is not None or '@' in search:
        # 1. find the user
        # Invoice links use the stable account ID, even if the email changed.
        condition = "id = :user_id" if user_id is not None else "LOWER(email) = LOWER(:email)"
        parameters = {"user_id": int(user_id)} if user_id is not None else {"email": search}
        user_row = db.session.execute(text(f"""
            SELECT id, name, email, phone, expirationtime, disabled
            FROM tc_users
            WHERE {condition}
            LIMIT 1
        """), parameters).fetchone()

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
            """).bindparams(bindparam("gids", expanding=True)), {"gids": tuple(group_ids)}).scalars().all()
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
        """).bindparams(bindparam("dids", expanding=True))
        device_rows = db.session.execute(devices_sql, {"dids": tuple(device_ids)}).fetchall()

        device_profiles = _build_device_profiles(device_rows)

        return jsonify({
            "user": _format_user(user_row),
            "devices": device_profiles,
            "truncated": False
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
          OR  d.phone       LIKE :phone ESCAPE '!'
          OR  d.name        LIKE :name ESCAPE '!'
        ORDER BY d.id
        LIMIT 50
    """)
    device_rows = db.session.execute(device_sql, {
        "search": search,
        "name":   f"%{_escape_like(search)}%",
        "phone":  f"%{_escape_like(search)}%"
    }).fetchall()

    if not device_rows:
        return jsonify({"error": "Device not found"}), 404

    device_profiles = _build_device_profiles(device_rows)
    return jsonify(device_profiles)


# ───────────────────────── helper formatters ───────────────────────── #

def _format_user(row):
    return {
        "id": row.id,
        "name":  row.name,
        "email": mask_email(row.email),
        "phone": mask_phone(row.phone),
        "expiry": row.expirationtime.isoformat() if row.expirationtime else None,
        "status": get_account_status(row.expirationtime, row.disabled)
    }

def _build_device_profile(device, user_profiles):
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

def _build_device_profiles(devices):
    if not devices:
        return []
    ids = [device.device_id for device in devices]
    users_sql = text("""
        SELECT d.id AS linked_device_id, u.id, u.name, u.email, u.phone, u.expirationtime, u.disabled
        FROM tc_devices d
        JOIN tc_user_device ud ON ud.deviceid = d.id
        JOIN tc_users u ON u.id = ud.userid
        WHERE d.id IN :ids
        UNION
        SELECT d.id AS linked_device_id, u.id, u.name, u.email, u.phone, u.expirationtime, u.disabled
        FROM tc_devices d
        JOIN tc_user_group ug ON ug.groupid = d.groupid
        JOIN tc_users u ON u.id = ug.userid
        WHERE d.id IN :ids
    """).bindparams(bindparam("ids", expanding=True))
    by_device = {device_id: [] for device_id in ids}
    for row in db.session.execute(users_sql, {"ids": ids}).fetchall():
        if row.id not in exclude_users_list:
            by_device[row.linked_device_id].append(_format_user(row))
    return [_build_device_profile(device, by_device[device.device_id]) for device in devices]


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




