#======================SCAN CYCLE FOR BAGFILTER==============
#import all necessary libraries
from app.database import SessionLocal
from app.models import Equipments, AnalogTags, DigitalTags, Alarm
import asyncio
from sqlalchemy import and_

#define runnimg condition function for the baghouse
async def running():
    db = SessionLocal()

    while True:
        #for the analog instruments values at the baghouse
        analog_id = ["KBF-DP-800", "KBF-VT-802", "KBF-TT-803", "KBF-PT-804"]
        analog_rows = []
        for id in analog_id:
            analog_= db.query(AnalogTags).filter(AnalogTags.tag_id == id).first()
            analog_rows.append(analog_)
        
        #create a running condition for the analog vals
        all_analog_ok = True
        for data in analog_rows:
            if data.process_val <= data.l2_val or data.process_val >= data.h2_val:
                all_analog_ok = False 
                break

        #digital io
        digital_id = ["KBF-MD-801-XS", "KBF-CS-805"]

        digital_rows = []
        for id in digital_id:
            digital_ = db.query(DigitalTags).filter(DigitalTags.tag_id == id).first()
            digital_rows.append(digital_)

        #set running condition for the digital io
        all_digital_ok = True
        for data in digital_rows:
            if data.binary_state == False:
                all_digital_ok = False

        #set running status
        equip_id = ["KBF-MD-801-XS", "KBF-CS-805"]
        if all_analog_ok == True and all_digital_ok == True:
            
            for id in equip_id:
                row = db.query(Equipments).filter(Equipments.tag_id == id).first()

                row.status = "RUNNING"
                
        else:
            for id in equip_id:
                row = db.query(Equipments).filter(Equipments.tag_id == id).first()
                
                row.status = "STOPPED"
        
        db.commit()
        
        await asyncio.sleep(1)


#create alarm status function 
async def alarm():
    db = SessionLocal()

    #create a continous loop
    while True:
        #analog values
        analog_id = ["KBF-DP-800", "KBF-VT-802", "KBF-TT-803", "KBF-PT-804"]
        
        #for every analog sensors, iterate the process_vals and compare to the alarm value while setting a conditional statement
        for tag_id in analog_id:
            row_query = db.query(AnalogTags).filter(AnalogTags.tag_id == tag_id).first()


            if row_query.process_val <= row_query.l2_val:
                alarm_type = 'L2'
                alarm_active = True
                alarm_descr = f'{tag_id} L2 alarm'

            elif row_query.process_val <= row_query.l1_val:
                alarm_type = 'L1'
                alarm_active = True
                alarm_descr =  f'{tag_id} L1 alarm'
                
            elif row_query.process_val >= row_query.h2_val:
                alarm_type = 'H2'
                alarm_active = True
                alarm_descr =  f'{tag_id} H2 alarm'
                
            elif row_query.process_val >= row_query.h1_val:
                alarm_type = 'H1'
                alarm_active = True
                alarm_descr =  f'{tag_id} H1 alarm'
                
            else:
                #reset alarm_active to False when the value has gone back to normal
                check_val = db.query(Alarm).filter(and_(
                    Alarm.tag_id == tag_id,
                    Alarm.alarm_active == True
                )).first()

                if check_val:
                    check_val.alarm_active = False
                    db.commit()
                continue

            #check if alarm exist in other not to return multiple row of same alarm on loop
            existing_alarm = db.query(Alarm).filter(and_(
                Alarm.tag_id == tag_id,
                Alarm.alarm_type == alarm_type,
                Alarm.alarm_active == True
            )).first()

            if existing_alarm:
                continue


            alarm = Alarm(tag_id = row_query.tag_id, alarm_type = alarm_type, alarm_active = alarm_active, alarm_descr = alarm_descr)
            db.add(alarm)
            db.commit()

        await asyncio.sleep(1)


#define helper function for bagfilter trip — updates Equipments and DigitalTags
def execute_bagfilter_trip(db):

    #set bagfilter motor drive running status to tripped on the equipments table
    equip_run_status = db.query(Equipments).filter(Equipments.tag_id == "KBF-MD-801-XS").first()
    if equip_run_status:
        equip_run_status.status = "TRIPPED"

    #set bagfilter motor drive fault feedback and cleaner solenoid status to alarm
    equip_tag = ["KBF-MD-801-XF", "KBF-CS-805"]
    for equip in equip_tag:
        equip_fault_status = db.query(Equipments).filter(Equipments.tag_id == equip).first()
        if equip_fault_status:
            equip_fault_status.status = "ALARM"

    #query the digital_tags table, set running_status to False and fault_status to True
    dig_run_status = db.query(DigitalTags).filter(DigitalTags.tag_id == "KBF-MD-801-XS").first()
    if dig_run_status:
        dig_run_status.binary_state = False

    dig_fault_status = db.query(DigitalTags).filter(DigitalTags.tag_id == "KBF-MD-801-XF").first()
    if dig_fault_status:
        dig_fault_status.binary_state = True


#trip and reset logic
async def trip_reset():
    db = SessionLocal()

    while True:
        #check if L2 or H2 alarm is active on bidirectional tags and then trip the equipment
        tags = ["KBF-DP-800", "KBF-PT-804"]  #for both directions (L2 and H2)
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

                #query to check if the alarm is still active after the countdown
                still_active = db.query(Alarm).filter(and_(
                    Alarm.tag_id == tag,
                    Alarm.alarm_type.in_(["L2", "H2"]),
                    Alarm.alarm_active == True
                )).first()

                #if alarm cleared during countdown, prevent the trip
                if not still_active:
                    continue

                #if the alarm is still active, execute the trip
                execute_bagfilter_trip(db)
                db.commit()

            else:
                continue

        #repeat for unidirectional H2 alarm (high temperature trips the bagfilter)
        alarm_query = db.query(Alarm).filter(and_(
            Alarm.tag_id == "KBF-TT-803",
            Alarm.alarm_type == "H2",
            Alarm.alarm_active == True
        )).first()

        if alarm_query:

            #create a time delay of 120sec before tripping
            await asyncio.sleep(120)

            #query to check if the alarm is still active after the countdown
            still_active = db.query(Alarm).filter(and_(
                Alarm.tag_id == "KBF-TT-803",
                Alarm.alarm_type == "H2",
                Alarm.alarm_active == True
            )).first()

            #if alarm cleared during countdown, prevent the trip
            if not still_active:
                await asyncio.sleep(1)
                continue

            #if the alarm is still active, execute the trip
            execute_bagfilter_trip(db)
            db.commit()

        await asyncio.sleep(1)