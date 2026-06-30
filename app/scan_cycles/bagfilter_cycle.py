#======================SCAN CYCLE FOR BAGFILTER==============
#import all necessary libraries
from database import SessionLocal
from models import Equipments, AnalogTags, DigitalTags, Alarm
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
            analog_ = db.query(AnalogTags).filter(AnalogTags.tag_id == id).first()
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