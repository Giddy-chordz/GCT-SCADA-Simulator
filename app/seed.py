#======SEEDING COLUMN TAGS======
from database import SessionLocal
from models import Equipments, AnalogTags, DigitalTags, Alarm, GroupStatus

db = SessionLocal()


equipments = [
    #=========================== VRM AND AUXILIARIES ====================
    Equipments(tag_id = "VRM-MD-010", equip_description = "Mill main drive command", io_type = "DO"),
    Equipments(tag_id = "VRM-MD-010-XS", equip_description = "Mill main drive running feedback", io_type = "DI"),
    Equipments(tag_id = "VRM-MD-010-XF", equip_description = "Mill main drive fault feedback", io_type = "DI"), 

    Equipments(tag_id = "VRM-MD-020", equip_description = "Separator drive command", io_type = "DO"),
    Equipments(tag_id = "VRM-MD-020-XS", equip_description = "Separator drive running feedback", io_type = "DI"),
    Equipments(tag_id = "VRM-MD-020-XF", equip_description = "Separator drive fault feedback", io_type = "DI"), 

    Equipments(tag_id = "VRM-MD-070", equip_description = "Hydraulic pump command", io_type = "DO"),
    Equipments(tag_id = "VRM-MD-070-XS", equip_description = "Hydraulic pump running feedback", io_type = "DI"),
    Equipments(tag_id = "VRM-MD-070-XF", equip_description = "Hydraulic pump fault feedback", io_type = "DI"), 

    Equipments(tag_id = "VRM-TT-030", equip_description = "Mill inlet temperature transmitter", io_type = "AI"),
    Equipments(tag_id = "VRM-TT-031", equip_description = "Mill outlet temperature transmitter", io_type = "AI"), 

    Equipments(tag_id = "VRM-VT-040", equip_description = "Mill body vibration", io_type = "AI"),
    Equipments(tag_id = "VRM-VT-041", equip_description = "Mill main drive vibration", io_type = "AI"), 
    Equipments(tag_id = "VRM-VT-042", equip_description = "Mill gearbox vibration", io_type = "AI"),

    Equipments(tag_id = "VRM-PT-060", equip_description = "Hydraulic Pressure transmitter", io_type = "AI"),

    Equipments(tag_id = "VRM-LSH-080", equip_description = "Oil tank high level", io_type = "DI"),
    Equipments(tag_id = "VRM-LSL-081", equip_description = "Oil tank low level", io_type = "DI"),

    #==================KILN AND GCT SECTION===========================
    Equipments(tag_id = "GCT-TT-101", equip_description = "Inlet temperature transmitter", io_type = "AI"),
    Equipments(tag_id = "GCT-TT-102", equip_description = "Outlet temperature transmitter", io_type = "AI"),

    Equipments(tag_id = "GCT-FT-201", equip_description = "Air flow transmitter", io_type = "AI"),
    Equipments(tag_id = "GCT-FT-202", equip_description = "Water flow transmitter", io_type = "AI"),

    Equipments(tag_id = "GCT-LSH-301", equip_description = "Water tank high level switch", io_type = "DI"),
    Equipments(tag_id = "GCT-LSH-302", equip_description = "Water tank low level switch", io_type = "DI"),

    Equipments(tag_id = "GCT-MP-601", equip_description = "Water pump command", io_type = "DO"),
    Equipments(tag_id = "GCT-MP-601-XS", equip_description = "Water pump running feedback", io_type = "DI"),
    Equipments(tag_id = "GCT-MP-601-XF", equip_description = "Water pump fault feedback", io_type = "DI"),

    Equipments(tag_id = "KLN-KD-701", equip_description = "Kiln main drive command", io_type = "DO"),
    Equipments(tag_id = "KLN-KD-701-XS", equip_description = "Kiln main drive running feedback", io_type = "DI"),
    Equipments(tag_id = "KLN-KD-701-XF", equip_description = "Kiln main drive fault feedback", io_type = "DI"),

    Equipments(tag_id = "KLN-BG-702", equip_description = "Kiln barring gear command", io_type = "DO"),
    Equipments(tag_id = "KLN-BG-702-XS", equip_description = "Kiln barring gear running feedback", io_type = "DI"),
    Equipments(tag_id = "KLN-BG-702-XF", equip_description = "Kiln barring gear fault feedback", io_type = "DI"),

    Equipments(tag_id = "KLN-XS-001", equip_description = "Kiln group running status", io_type = "CALC"),
    Equipments(tag_id = "KLN-XS-002", equip_description = "Kiln group trip latch status", io_type = "CALC"),

    #=======================BAG FILTER SECTION===================
    Equipments(tag_id = "KBF-DP-800", equip_description = "Bag house differntial pressure transmitter", io_type = "AI"),    
    
    Equipments(tag_id = "KBF-MD-801", equip_description = "ID fan command", io_type = "DO"),
    Equipments(tag_id = "KBF-MD-801-XS", equip_description = "ID fan running feedback", io_type = "DI"),
    Equipments(tag_id = "KBF-MD-801-XF", equip_description = "ID fan fault feedback", io_type = "DI"),

    Equipments(tag_id = "KBF-VT-802", equip_description = "ID fan bearing vibration", io_type = "AI"),    
    Equipments(tag_id = "KBF-TT-803", equip_description = "ID fan bearing temprature", io_type = "AI"), 

    Equipments(tag_id = "KBF-PT-804", equip_description = "Air receiver pressure", io_type = "AI"), 

    Equipments(tag_id = "KBF-CS-805", equip_description = "Local controller communication/active status", io_type = "DI"), 
]

#-----------ROLLER POSITION-----------------
for i in range(50, 54):
    equipments.append(
        Equipments(tag_id = f"VRM-LS-{i}-ZSU",
                equip_description = f"Roller {i} Up-mode",
                    io_type = "DI"
        )
    )

for i in range(50, 54):
    equipments.append(
        Equipments(tag_id = f"VRM-LS-{i}-ZSD",
                equip_description = f"Roller {i} grinding mode",
                    io_type = "DI"
        )
    )

#-------------air lances valve commands----------------
for i in range(401, 411):
    equipments.append(
        Equipments(tag_id = f"GCT-XV-{i}", 
                   equip_description = f"Air lances valve {i}",
                   io_type = "DO")
    )

#----------------air lances valve open feedback---------------
for i in range(401, 411):
    equipments.append(
        Equipments(tag_id = f"GCT-XV-{i}-ZSO", 
                   equip_description = f"Air lances valve {i} open position feedback",
                   io_type = "DI")
    )

#----------------air lances valve closed position feedback--------------
for i in range(401, 411):
    equipments.append(
        Equipments(tag_id = f"GCT-XV-{i}-ZSC", 
                   equip_description = f"Air lances valve {i} closed position feedback",
                   io_type = "DI")
    )

#--------------for water lances valve command--------------
for i in range(501, 511):
    equipments.append(
        Equipments(tag_id = f"GCT-XV-{i}", 
                   equip_description = f"Water lances valve {i}",
                   io_type = "DO")
    )

#---------------for water lances valve open feedback-----------------
for i in range(501, 511):
    equipments.append(
        Equipments(tag_id = f"GCT-XV-{i}-ZSO", 
                   equip_description = f"Water lances valve {i} open position feedback",
                   io_type = "DI")
    )

#----------------for water lances valve close position feedback----------------------
for i in range(501, 511):
    equipments.append(
        Equipments(tag_id = f"GCT-XV-{i}-ZSC", 
                   equip_description = f"Water lances valve {i} close position feedback",
                   io_type = "DI")
    )


#=======================ANALOG TAGS================================
analog_tags = [
    #VRM inlet and outlet temperature
    AnalogTags(tag_id = "VRM-TT-030", process_val = 30, param_unit = "°C", l1_val = 150, l2_val = 130, h1_val = 250, h2_val = 280),
    AnalogTags(tag_id = "VRM-TT-031", process_val = 30, param_unit = "°C", l1_val = None, l2_val = None, h1_val = None, h2_val = None),

    #VRM vibrations; millbody, drive and gb
    AnalogTags(tag_id = "VRM-VT-040", process_val = 0, param_unit = "mm/s", l1_val = None, l2_val = None, h1_val = 8, h2_val = 10),
    AnalogTags(tag_id = "VRM-VT-041", process_val = 0, param_unit = "mm/s", l1_val = None, l2_val = None, h1_val = 5, h2_val = 7),
    AnalogTags(tag_id = "VRM-VT-042", process_val = 0, param_unit = "mm/s", l1_val = None, l2_val = None, h1_val = 5, h2_val = 7),

    #VRM roller hydraulic pressure
    AnalogTags(tag_id = "VRM-PT-060",  process_val = 0, param_unit = "bar", l1_val = 60, l2_val = 50, h1_val = 220, h2_val = 240),

    #GCT inlet and outlet temperature transmitters
    AnalogTags(tag_id = "GCT-TT-101", process_val = 30, param_unit = "°C", l1_val = None, l2_val = None, h1_val = None, h2_val = None),
    AnalogTags(tag_id = "GCT-TT-102", process_val = 30, param_unit = "°C", l1_val = 70, l2_val = 50, h1_val = 120, h2_val = 140),

    #GCT water and air flow
    AnalogTags(tag_id = "GCT-FT-201", process_val = 0, param_unit = "L/min", l1_val = 800, l2_val = 500, h1_val = None, h2_val = None),
    AnalogTags(tag_id = "GCT-FT-202", process_val = 0, param_unit = "L/min", l1_val = 5, l2_val = 2, h1_val = 25, h2_val = 30),

    #baghouse differential pressure
    AnalogTags(tag_id = "KBF-DP-800", process_val = 0, param_unit = "mbar", l1_val = 2, l2_val = 1, h1_val = 15, h2_val = 18),

    #ID fan analog signals
    AnalogTags(tag_id = "KBF-VT-802", process_val = 0, param_unit = "mm/s", l1_val = None, l2_val = None, h1_val = 5, h2_val = 7),
    AnalogTags(tag_id = "KBF-TT-803", process_val = 30, param_unit = "°C", l1_val = None, l2_val = None, h1_val = 80, h2_val = 95),  

    #Air receiver tank pressure
    AnalogTags(tag_id = "KBF-PT-804", process_val = 0, param_unit = "mbar", l1_val = 5.5, l2_val = 4.5, h1_val = None, h2_val = None)  
]

#=======================DIGITAL TAGS=============================
digital_tags = [
    #-------mill drive command, running and fault-------------
    DigitalTags(tag_id = "VRM-MD-010", binary_state = False),
    DigitalTags(tag_id = "VRM-MD-010-XS", binary_state = False),
    DigitalTags(tag_id = "VRM-MD-010-XF"),

    #-------separator drive command, running and fault--------
    DigitalTags(tag_id = "VRM-MD-020"),
    DigitalTags(tag_id = "VRM-MD-020-XS"),
    DigitalTags(tag_id = "VRM-MD-020-XF"),

    #--------hydraulic drive command, running and fault
    DigitalTags(tag_id = "VRM-MD-070"),
    DigitalTags(tag_id = "VRM-MD-070-XS"),
    DigitalTags(tag_id = "VRM-MD-070-XF"),

    #------------hydralic tank level---------
    DigitalTags(tag_id = "VRM-LSH-080"),
    DigitalTags(tag_id = "VRM-LSL-081"),
    
    #---------GCT water tank level-----------
    DigitalTags(tag_id = "GCT-LSH-301"),
    DigitalTags(tag_id = "GCT-LSH-302"),

    #----------GCT water pump command, running and fault
    DigitalTags(tag_id = "GCT-MP-601"),
    DigitalTags(tag_id = "GCT-MP-601-XS"),
    DigitalTags(tag_id = "GCT-MP-601-XF"),

    #----------Kiln main drive command, running and fault
    DigitalTags(tag_id = "KLN-KD-701"),
    DigitalTags(tag_id = "KLN-KD-701-XS"),
    DigitalTags(tag_id = "KLN-KD-701-XF"),

    #----------Kiln barring gear command, running and fault
    DigitalTags(tag_id = "KLN-BG-702"),
    DigitalTags(tag_id = "KLN-BG-702-XS"),
    DigitalTags(tag_id = "KLN-BG-702-XF"), 

    #----------ID fan command, running and fault
    DigitalTags(tag_id = "KBF-MD-801"),
    DigitalTags(tag_id = "KBF-MD-801-XS"),
    DigitalTags(tag_id = "KBF-MD-801-XF"), 

    #-----------bag filter local controller
    DigitalTags(tag_id = "KBF-CS-805")
]

#-----------ROLLER POSITION-----------------
for i in range(50, 54):
    digital_tags.append(
        DigitalTags(tag_id = f"VRM-LS-{i}-ZSU")
    )

for i in range(50, 54):
    digital_tags.append(
        DigitalTags(tag_id = f"VRM-LS-{i}-ZSD") #grinding mode
    ) 

#-------------air lances valve commands----------------
for i in range(401, 411):
    digital_tags.append(
        DigitalTags(tag_id = f"GCT-XV-{i}")
    )

#----------------air lances valve open feedback---------------
for i in range(401, 411):
    digital_tags.append(
        DigitalTags(tag_id = f"GCT-XV-{i}-ZSO")
    )

#----------------air lances valve closed position feedback--------------
for i in range(401, 411):
    digital_tags.append(
        DigitalTags(tag_id = f"GCT-XV-{i}-ZSC")
    )

#--------------for water lances valve command--------------
for i in range(501, 511):
    digital_tags.append(
        DigitalTags(tag_id = f"GCT-XV-{i}")
    )

#---------------for water lances valve open feedback-----------------
for i in range(501, 511):
    digital_tags.append(
        DigitalTags(tag_id = f"GCT-XV-{i}-ZSO")
    )

#----------------for water lances valve close position feedback----------------------
for i in range(501, 511):
    digital_tags.append(
        DigitalTags(tag_id = f"GCT-XV-{i}-ZSC")
    )


#=========GROUP STATUS==========
group_status = [
    GroupStatus(tag_id = 'KLN-XS-001'),
    GroupStatus(tag_id = 'KLN-XS-002')
]

db.add_all(equipments)
db.commit()

db.add_all(analog_tags)
db.commit()

db.add_all(digital_tags)
db.commit()

db.add_all(group_status)
db.commit()

db.close()

print("Seeding completed.....")