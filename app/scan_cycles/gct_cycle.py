#===========SCAN_CYCLE FOR THE GCT SECTION========
from database import SessionLocal
from sensor_data import AnalogSensor, sensors
from models import Equipments, AnalogTags, DigitalTags, Alarm, GroupStatus
import asyncio

#set running condition for the system
async def running():
    db = SessionLocal()

    while True:
        #the analog_sensors in the gct section
        analog_tags = []