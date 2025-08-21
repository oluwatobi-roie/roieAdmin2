"""
This adds new devices to the system
devices can be added in bulk or one at a time.
Bulk mode allows adding multiple devices with a default name a user can assign.
Maximum bulk size is capped at 15 devices to prevent overload.
Single mode allows adding a device with a specific name, phone number, and unique ID.
# It also assigns the device to a group, defaulting to "Roie Admin" if not specified.
The code handles ID allocation using a simple  locking mechanism to ensure no conflicts.
It retries once in case of a conflict. 
"""


from .common import request, jsonify, db, text, IntegrityError, random
from routes.devices import device_bp


MAX_BULK = 15          # hard cap
# Full api path: /api/devices/add
@device_bp.route('/add', methods=['POST'])
def add_device():
    data = request.get_json()
    mode = data.get("mode", "single")

    if mode == "bulk":
        return _add_bulk_devices(data)
    elif mode == "single":
        return _add_single_device(data)
    else:
        return jsonify({"error": "Invalid mode"}), 400    


# Helper function to get avaulable Ids from database
def _next_free_ids(count, reserved_start=11):
    """
    Return a list of `count` unused IDs (≥ reserved_start).
    Assumes the caller already holds a FOR UPDATE lock on tc_devices.
    """
    used_ids = db.session.execute(
        text("SELECT id FROM tc_devices")
    ).scalars().all()
    used = set(used_ids)

    candidate = reserved_start
    free = []
    while len(free) < count:
        if candidate not in used:
            free.append(candidate)
        candidate += 1
    return free


# Function to handle bulk device addition
def _add_bulk_devices(data):
    template = data.get("name", "bulkadd")
    total    = min(int(data.get("count", 1)), MAX_BULK)
    base_uid = random.randint(1000000000, 9999999999)

    # Fetch RoieAdmin group id once
    group_row = db.session.execute(
        text("SELECT id FROM tc_groups WHERE name = :g"),
        {"g": "Roie Admin"}
    ).fetchone()
    if not group_row:
        return jsonify({"error": "Group 'Roie Admin' not found"}), 404
    group_id = group_row.id

    attempts = 0
    while attempts < 2:          # simple retry once
        try:
            with db.session.begin_nested():  # ← transactional scope
                # lock existing ids
                db.session.execute(text("SELECT id FROM tc_devices FOR UPDATE"))

                free_ids = _next_free_ids(total)  # safe: we hold the lock
                inserted = []

                for i in range(total):
                    dev_id   = free_ids[i]
                    name     = f"{template}-{i+1}"
                    uniqueid = int(f"{base_uid}{i+1}")

                    db.session.execute(text("""
                        INSERT INTO tc_devices (id, name, uniqueid, groupid, status)
                        VALUES (:id, :name, :uid, :gid, 'unknown')
                    """), {
                        "id":  dev_id,
                        "name": name,
                        "uid": uniqueid,
                        "gid": group_id
                    })
                    inserted.append({"id": dev_id, "name": name, "uniqueid": uniqueid})

            # commit succeeded
            db.session.commit()  # commit the transaction
            return jsonify({
                "message": f"{len(inserted)} devices added.",
                "devices": inserted
            })

        except IntegrityError:
            # someone grabbed an ID between SELECT and INSERT – very rare
            db.session.rollback()
            attempts += 1

    return jsonify({"error": "Could not allocate IDs, please retry."}), 409


# Function to handle single device addition
def _add_single_device(data):
    
    name     = data.get("name")
    phone    = data.get("phone")
    uniqueid = data.get("uniqueid")
    group_nm = data.get("group", "Roie Admin")
    
    if not all([name, phone, uniqueid]):
        return jsonify({"error": "name, phone, uniqueid required"}), 400

    group_id = db.session.execute(
        text("SELECT id FROM tc_groups WHERE name = :g"), {"g": group_nm}
    ).scalar()
    if not group_id:
        return jsonify({"error": f"Group '{group_nm}' not found"}), 404

    attempts = 0
    while attempts < 2:
        try:
            with db.session.begin_nested():
                db.session.execute(text("SELECT id FROM tc_devices FOR UPDATE"))
                next_id = _next_free_ids(1)[0]

                db.session.execute(text("""
                    INSERT INTO tc_devices (id, name, uniqueid, phone, groupid, status)
                    VALUES (:id, :name, :uid, :phone, :gid, 'unknown')
                """), {
                    "id": next_id, "name": name, "uid": uniqueid,
                    "phone": phone, "gid": group_id
                })
            db.session.commit()  # commit the transaction
            return jsonify({
                "message": "Device added.",
                "device": {"id": next_id, "name": name, "uniqueid": uniqueid, "phone": phone}
            })

        except IntegrityError:
            db.session.rollback()
            attempts += 1

    return jsonify({"error": "ID conflict, try again"}), 409
