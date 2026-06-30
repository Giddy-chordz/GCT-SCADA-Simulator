#=============CONTINOUSLY UPDATING SENSOR READINGS==========
from database import SessionLocal
from models import AnalogTags
from sensor_data import AnalogSensor, sensors
import asyncio

#create function to update the process values in the analog_tag table
async def sensor_vals():
    db = SessionLocal()

    while True:
        for id, data in sensors.items():

            #query the table and filte when tag_id == id
            row = db.query(AnalogTags).filter(AnalogTags.tag_id == id).first()
            
            #update the process_val if the row exists
            if row:
                row.process_val = data.read()

            #commit the val to the table
            db.commit()

        await asyncio.sleep(1)

