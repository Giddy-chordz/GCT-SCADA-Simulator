#===========SCAN_CYCLE FOR THE GCT SECTION========
from database import SessionLocal
from models import Equipments, AnalogTags, DigitalTags, Alarm, GroupStatus
from sqlalchemy import and_
import asyncio


#set running condition for the system
async def running():
    db = SessionLocal()

    while True:

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

        #set running status in the equipment table
        equip_id = ["KLN-KD-701-XS", "KLN-XS-001"]
        for id in equip_id:
            equip_status = db.query(Equipments).filter(Equipments.tag_id == id).first()
            if equip_status:
                if all_analog_ok and digital_ok:
                    equip_status.status = "RUNNING"
                else:
                    equip_status.status = "STOPPED"

        db.commit()
        await asyncio.sleep(1)


#set alarm
async def alarm():
    db = SessionLocal()

    #create a continous loop
    while True:
        analog_tags = ["GCT-TT-102", "GCT-FT-201", "GCT-FT-202"]

        #for every analog sensor, iterate the process_vals and compare to the alarm value
        for tag in analog_tags:

            #query the analog_tags table to check if alarm
            row_query = db.query(AnalogTags).filter(AnalogTags.tag_id == tag).first()
            if not row_query:
                continue

            #compare the process values to the alarm values
            if row_query.process_val <= row_query.l2_val:
                alarm_type = "L2"
                alarm_active = True
                alarm_descr = f"{tag} L2 alarm"

            elif row_query.process_val <= row_query.l1_val:
                alarm_type = "L1"
                alarm_active = True
                alarm_descr = f"{tag} L1 alarm"

            elif row_query.process_val >= row_query.h2_val:
                alarm_type = "H2"
                alarm_active = True
                alarm_descr = f"{tag} H2 alarm"

            elif row_query.process_val >= row_query.h1_val:
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
        await asyncio.sleep(1)


#define helper function for kiln trip — updates Equipments, DigitalTags and GroupStatus
def execute_kiln_trip(db):

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
    db = SessionLocal()

    while True:
        #check if L2 or H2 alarm is active and then stop the equipment

        tags = ["GCT-TT-102", "GCT-FT-202"]  #for both directions (L2 and H2)
        for tag in tags:

            #query to identify the tag_id with active L2 or H2 alarm
            alarm_query = db.query(Alarm).filter(and_(
                Alarm.tag_id == tag,
                Alarm.alarm_type.in_(["L2", "H2"]),
                Alarm.alarm_active == True
            )).first()

            #condition to check if H2 or L2 alarm is active
            if alarm_query:

                #create a time delay of 120sec before tripping
                await asyncio.sleep(120)

                #in order not to stop the equipment when the alarm has cleared during countdown
                #query to check if the alarm is still active
                still_active = db.query(Alarm).filter(and_(
                    Alarm.tag_id == tag,
                    Alarm.alarm_type.in_(["L2", "H2"]),
                    Alarm.alarm_active == True
                )).first()

                #if alarm is not active, stop the timer and prevent the trip
                if not still_active:
                    continue

                #if the alarm is therefore still active, execute the trip
                execute_kiln_trip(db)
                db.commit()

            else:
                continue

        #repeat for unidirectional (L2 airflow alarm to trip the kiln)
        alarm_query = db.query(Alarm).filter(and_(
            Alarm.tag_id == "GCT-FT-201",
            Alarm.alarm_type == "L2",
            Alarm.alarm_active == True
        )).first()

        if alarm_query:

            #create a time delay of 120sec before tripping
            await asyncio.sleep(120)

            #in order not to stop the equipment when the alarm has cleared during countdown
            #query to check if the alarm is still active
            still_active = db.query(Alarm).filter(and_(
                Alarm.tag_id == "GCT-FT-201",
                Alarm.alarm_type == "L2",
                Alarm.alarm_active == True
            )).first()

            #if alarm is not active, stop the timer and prevent the trip
            if not still_active:
                await asyncio.sleep(1)
                continue

            #if the alarm is therefore still active, execute the trip
            execute_kiln_trip(db)
            db.commit()

        await asyncio.sleep(1)