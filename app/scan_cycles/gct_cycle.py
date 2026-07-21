#===========SCAN_CYCLE FOR THE GCT SECTION========
from database import SessionLocal
from models import Equipments, AnalogTags, DigitalTags, Alarm, GroupStatus
from sqlalchemy import and_
import asyncio
from datetime import datetime

#tracking the trip state for the kiln equipment
trip_state = {
    "active": False,
    "remaining": 0,
    "reason": None,
    "equipment": None,
    "started_at": None,
}

#set running condition for the system
async def running():
    print("gct running")
    while True:
        # Fresh session every iteration — ensures HTTP command endpoint changes
        # (e.g. manual_override flag) are immediately visible to the scan cycle.
        db = SessionLocal()
        try:
            #the analog_sensors in the gct section
            analog_tags = ["GCT-TT-102", "GCT-FT-201", "GCT-FT-202"]
            all_analog_ok = True

            #loop through the instruments to ensure they are within safe operating band
            for tag in analog_tags:

                #query the AnalogTags to check their values
                row = db.query(AnalogTags).filter(AnalogTags.tag_id == tag).first()

                #check if the process value is not below l2 or above h2
                if row and (row.process_val <= row.l2_val or row.process_val >= row.h2_val):
                    all_analog_ok = False
                    break

            #for the digital feedbacks in the gct/kiln section
            dig_query = db.query(DigitalTags).filter(DigitalTags.tag_id == "KLN-KD-701-XS").first()

            #check if binary_state is true to confirm running
            digital_ok = True
            if not dig_query or not dig_query.binary_state:
                digital_ok = False

            # Set running status on the DO command tag and its XS/group-status siblings.
            # Skip tags whose DO equipment row has manual_override set — the operator
            # command takes priority until a genuine trip clears the flag.
            do_equip = db.query(Equipments).filter(Equipments.tag_id == "KLN-KD-701").first()
            if not (do_equip and do_equip.manual_override):
                new_status = "RUNNING" if (all_analog_ok and digital_ok) else "STOPPED"
                for tag_id in ["KLN-KD-701-XS", "KLN-XS-001"]:
                    equip_status = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
                    if equip_status:
                        equip_status.status = new_status
                if do_equip:
                    do_equip.status = new_status

            db.commit()
        finally:
            db.close()

        await asyncio.sleep(1)


#set alarm
async def alarm():

    #create a continous loop
    while True:
        db = SessionLocal()
        try:
            analog_tags = ["GCT-TT-102", "GCT-FT-201", "GCT-FT-202"]

            #for every analog sensor, iterate the process_vals and compare to the alarm value
            for tag in analog_tags:

                #query the analog_tags table to check if alarm
                row_query = db.query(AnalogTags).filter(AnalogTags.tag_id == tag).first()
                
                if not row_query:
                    continue

                #compare the process values to the alarm values
                if row_query.l2_val is not None and row_query.process_val <= row_query.l2_val:
                    alarm_type = "L2"
                    alarm_active = True
                    alarm_descr = f"{tag} L2 alarm"

                elif row_query.l1_val is not None and row_query.process_val <= row_query.l1_val:
                    alarm_type = "L1"
                    alarm_active = True
                    alarm_descr = f"{tag} L1 alarm"

                elif row_query.h2_val is not None and row_query.process_val >= row_query.h2_val:
                    alarm_type = "H2"
                    alarm_active = True
                    alarm_descr = f"{tag} H2 alarm"

                elif row_query.h1_val is not None and row_query.process_val >= row_query.h1_val:
                    alarm_type = "H1"
                    alarm_active = True
                    alarm_descr = f"{tag} H1 alarm"

                else:
                    #if the alarm value has gone back to normal, reset the alarm_active to false
                    normal_val = db.query(Alarm).filter(and_(
                        Alarm.tag_id == tag,
                        Alarm.alarm_active == True
                    )).first()

                    if normal_val:
                        normal_val.alarm_active = False
                        db.commit()

                    continue

                #check if alarm exists in order to avoid creating multiple rows of same alarm on every iteration
                existing_alarm = db.query(Alarm).filter(and_(
                    Alarm.tag_id == tag,
                    Alarm.alarm_type == alarm_type,
                    Alarm.alarm_active == True
                )).first()

                if existing_alarm:
                    continue

                #if alarm, update the alarm table
                new_alarm = Alarm(tag_id=tag, alarm_type=alarm_type, alarm_active=alarm_active, alarm_descr=alarm_descr)
                db.add(new_alarm)

            db.commit()

        except Exception as e:
            print(f"[ALARM TASK CRASHED] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        finally:
            db.close()

        await asyncio.sleep(1)


#define helper function for kiln trip — updates Equipments, DigitalTags and GroupStatus
def execute_kiln_trip(db):

    # Safety interlock trip — clear manual override so the trip is not masked
    do_equip = db.query(Equipments).filter(Equipments.tag_id == "KLN-KD-701").first()
    if do_equip:
        do_equip.status = "TRIPPED"
        do_equip.manual_override = False

    #set kiln drive running status to tripped on the equipments table
    equip_run_status = db.query(Equipments).filter(Equipments.tag_id == "KLN-KD-701-XS").first()
    if equip_run_status:
        equip_run_status.status = "TRIPPED"

    #set kiln drive fault feedback and group status to alarm
    equip_tag = ["KLN-KD-701-XF", "KLN-XS-001"]
    for equip in equip_tag:
        equip_fault_status = db.query(Equipments).filter(Equipments.tag_id == equip).first()
        if equip_fault_status:
            equip_fault_status.status = "ALARM"

    #query the digital_tags table, set running_status to False and fault_status to True
    dig_run_status = db.query(DigitalTags).filter(DigitalTags.tag_id == "KLN-KD-701-XS").first()
    if dig_run_status:
        dig_run_status.binary_state = False

    dig_fault_status = db.query(DigitalTags).filter(DigitalTags.tag_id == "KLN-KD-701-XF").first()
    if dig_fault_status:
        dig_fault_status.binary_state = True

    #query the group_status table, set binary_status to False
    group_status = db.query(GroupStatus).filter(GroupStatus.tag_id == "KLN-XS-001").first()
    if group_status:
        group_status.binary_status = False


#trip and reset logic
async def trip_reset():
    while True:
        db = SessionLocal()
        try:
            tags = ["GCT-TT-102", "GCT-FT-202"]
            for tag in tags:
                alarm_query = db.query(Alarm).filter(and_(
                    Alarm.tag_id == tag,
                    Alarm.alarm_type.in_(["L2", "H2"]),
                    Alarm.alarm_active == True
                )).first()

                if alarm_query:
                    db.close()

                    trip_state["active"] = True
                    trip_state["remaining"] = 120
                    trip_state["reason"] = tag
                    trip_state["equipment"] = "KLN-KD-701"
                    trip_state["started_at"] = datetime.utcnow().isoformat()

                    db = SessionLocal()
                    for sec in range(120, 0, -1):
                        trip_state["remaining"] = sec
                        await asyncio.sleep(1)

                        db.close()
                        db = SessionLocal()

                        still_active = db.query(Alarm).filter(and_(
                            Alarm.tag_id == tag,
                            Alarm.alarm_type.in_(["L2", "H2"]),
                            Alarm.alarm_active == True
                        )).first()

                        if not still_active:
                            trip_state["active"] = False
                            trip_state["remaining"] = 0
                            break

                    if trip_state["active"]:
                        execute_kiln_trip(db)
                        db.commit()
                        trip_state["active"] = False
                        trip_state["remaining"] = 0

        finally:
            db.close()

        await asyncio.sleep(1)