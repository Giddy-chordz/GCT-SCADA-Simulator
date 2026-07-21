from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Enum, ForeignKey
from .database import Base
from datetime import datetime

#create a model for equpment tags and their status
class Equipments(Base):
    __tablename__ = "equipments"

    tag_id = Column(String, primary_key = True, nullable = False) #instrument/equipment code
    equip_description = Column(String, nullable = False)

    status = Column(Enum("RUNNING", "STOPPED", "TRIPPED", "ALARM", "UNKNOWN",name="equipment_status_enum"), default = "UNKNOWN") # current state
    io_type = Column(String, nullable = False) # AI, DI, DO, CALC

    # When True the scan cycle skips automatic status recalculation for this
    # drive and respects the manually set status.  Cleared only on a genuine
    # interlock trip (safety always wins) or when RESET is issued.
    manual_override = Column(Boolean, nullable = False, default = False)



#model for analog input signals
class AnalogTags(Base):
    __tablename__ = "analog_tags"

    tag_id = Column(String, ForeignKey("equipments.tag_id"), primary_key = True, nullable = False) #instrument/equipment code

    process_val = Column(Float, nullable = True) #instrument measured value
    param_unit = Column(String, nullable = True) #unit of measurement

    l1_val = Column(Float, nullable = True) # Low 1 alarm warning value
    l2_val = Column(Float, nullable = True) # Low2 alarm value

    h1_val = Column(Float, nullable = True)  # high 1 alarm warning value
    h2_val = Column(Float, nullable = True) # High2 alarm value

    time_stamp = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) #timestamp

#model for digital input
class DigitalTags(Base):
    __tablename__ = "digital_tags"

    tag_id = Column(String, ForeignKey("equipments.tag_id"), primary_key = True, nullable = False) #instrument/equipment code
    
    binary_state = Column(Boolean, default = False)

#model for alarms
class Alarm(Base):
    __tablename__ = "alarm"
    
    alarm_id = Column(Integer, primary_key=True, index = True)
    tag_id = Column(String, ForeignKey("equipments.tag_id"), nullable = False) #instrument/equipment code

    alarm_type = Column(String) #(H1/H2/L1/L2)

    alarm_active = Column(Boolean, default = False) # alarm is active or not
    alarm_acknowledged = Column(Boolean, default = False)

    alarm_descr = Column(String, nullable = True) #alarm description

    time_stamp = Column(DateTime, default=datetime.utcnow) #timestamp

#setup model for group status which is calculated besed on the interlock
class GroupStatus(Base):
    __tablename__ = "group_status"

    tag_id = Column(String, ForeignKey("equipments.tag_id"), primary_key = True, nullable = False) #instrument/equipment code

    binary_status = Column(Boolean, default = False)