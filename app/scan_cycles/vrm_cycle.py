#===========SCAN_CYCLE FOR THE VRM SECTION========
from app.database import SessionLocal
from app.models import Equipments, AnalogTags, DigitalTags, Alarm, GroupStatus
from sqlalchemy import and_
import asyncio


#set running condition for the system
async def run_sequence():
    db = SessionLocal()

    while True:

        #check the availability of all analog instruments
        analog_tags = ["VRM-TT-030", "VRM-PT-060", "VRM-VT-040", "VRM-VT-041", "VRM-VT-042"]
        all_analog_ok = True

        #loop through the instruments to ensure they are in no alarm values
        for tag in analog_tags:

            #query the AnalogTags to check their values
            row = db.query(AnalogTags).filter(AnalogTags.tag_id == tag).first()

            #check if the process value is not below l2 or above h2
            if row and (row.process_val <= row.l2_val or row.process_val >= row.h2_val):
                all_analog_ok = False
                break

        #check roller positions and confirm they are all in upmode
        roller_id = ["VRM-LS-50-ZSU", "VRM-LS-51-ZSU", "VRM-LS-52-ZSU", "VRM-LS-53-ZSU"]
        roller_up = True

        for roller in roller_id:
            roller_query = db.query(DigitalTags).filter(DigitalTags.tag_id == roller).first()

            #check if the binary state is true
            if not roller_query or not roller_query.binary_state:
                roller_up = False
                break

        #for the digital feedbacks in the VRM section
        digital_ok = True
        for tag in ["VRM-MD-020-XS", "VRM-MD-010-XS"]:
            dig_query = db.query(DigitalTags).filter(DigitalTags.tag_id == tag).first()

            #check if binary_state is true to confirm running
            if not dig_query or not dig_query.binary_state:
                digital_ok = False
                break

        #set running status in the equipment table
        equip_id = ["VRM-MD-020-XS", "VRM-MD-010-XS"]
        for id in equip_id:
            equip_status = db.query(Equipments).filter(Equipments.tag_id == id).first()
            if equip_status:
                if all_analog_ok and digital_ok and roller_up:
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
        analog_tags = ["VRM-TT-030", "VRM-PT-060", "VRM-VT-040", "VRM-VT-041", "VRM-VT-042"]

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


#define helper function for setting alarm status and equipment status
def execute_VRM_trip(db):

    #set VRM drive running status to tripped on the equipments table
    equip_run_status = db.query(Equipments).filter(Equipments.tag_id == "VRM-MD-010-XS").first()
    if equip_run_status:
        equip_run_status.status = "TRIPPED"

    #set VRM drive fault feedback status to alarm
    equip_tag = ["VRM-MD-010-XF"]
    for equip in equip_tag:
        equip_fault_status = db.query(Equipments).filter(Equipments.tag_id == equip).first()
        if equip_fault_status:
            equip_fault_status.status = "ALARM"

    #query the digital_tags table, set running_status to False and fault_status to True
    dig_run_status = db.query(DigitalTags).filter(DigitalTags.tag_id == "VRM-MD-010-XS").first()
    if dig_run_status:
        dig_run_status.binary_state = False

    dig_fault_status = db.query(DigitalTags).filter(DigitalTags.tag_id == "VRM-MD-010-XF").first()
    if dig_fault_status:
        dig_fault_status.binary_state = True


#trip and reset logic
async def trip_reset():
    db = SessionLocal()

    while True:
        #check if L2 or H2 alarm is active and then stop the equipment

        tags = ["VRM-TT-030", "VRM-PT-060"]  #for both directions (L2 and H2)
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
                execute_VRM_trip(db)
                db.commit()

            else:
                continue

        #repeat for unidirectional (H2 vibration alarm to trip the VRM)
        tag_id = ["VRM-VT-040", "VRM-VT-041", "VRM-VT-042"]
        for tag in tag_id:

            #query to identify the tag_id with active H2 alarm
            alarm_query = db.query(Alarm).filter(and_(
                Alarm.tag_id == tag,
                Alarm.alarm_type == "H2",
                Alarm.alarm_active == True
            )).first()

            if alarm_query:

                #create a time delay of 120sec before tripping
                await asyncio.sleep(120)

                #in order not to stop the equipment when the alarm has cleared during countdown
                #query to check if the alarm is still active
                still_active = db.query(Alarm).filter(and_(
                    Alarm.tag_id == tag,
                    Alarm.alarm_type == "H2",
                    Alarm.alarm_active == True
                )).first()

                #if alarm is not active, stop the timer and prevent the trip
                if not still_active:
                    continue

                #if the alarm is therefore still active, execute the trip
                execute_VRM_trip(db)
                db.commit()

            else:
                continue

        await asyncio.sleep(1)