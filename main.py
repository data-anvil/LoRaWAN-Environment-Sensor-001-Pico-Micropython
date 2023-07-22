import machine
import time
import gc

from machine import UART, SoftI2C, Pin, WDT
from utime import sleep_ms
from math import log, exp
from scd30 import SCD30 



#------------Resilience & Troubleshooting

# Initialise watchdog incase any loops crash
#wdt = WDT(timeout=8300)

# Initialise REPL logging
#import os
#logfile = open('log.txt', 'a')
#os.dupterm(logfile)

# Clean up memory
gc.collect()
gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

# Starts the clock that controls the program cycle
start_time = time.time()



#------------Serial Connections

# Setup I2C connection to SCD30 Module
i2c = SoftI2C(sda=Pin(2), scl=Pin(3))
scd30 = SCD30(i2c, 0x61)

# Setup UART connection to LoRa Module
loraModule = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))

# Setup UART connection to GPS Module
gpsModule = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))

# Used for timer based sensor only
# Initialise Pin 29 for Nano Power HAT shutdown at end of program
#GPIO_22 = machine.Pin(22, Pin.OUT)
#GPIO_22.value(0)


#------------Device Variables

# The elapsed time in seconds the program should run before restarting itself
end_time = start_time + 300

# When to give up on trying to make a LoRa connection and get ready for the restart
lora_end_time = start_time + 120

# When to give up on obtaining satellite fix and data (3 minute window)
gps_end_time = start_time + 90

# Temperature offset applied to the measurement received from SCD-30 sensor in Cº (two decimal places)
temp_offset = 0

# CO2 offset applied to the measurement received from SCD-30 sensor in ppm (whole number only)
co2_offset = 0

print('Everything Initialised')



#------------SCD-30 Temp & RH Data Gathering & Cleaning

# Configure number of seconds between sensor measurements (2 is the lowest)
scd30.set_measurement_interval(2)

sleep_ms(200)

# Wait for the SCD-30 to be ready
while scd30.get_status_ready() != 1:
    sleep_ms(200)

# Initial read to clear any erroneous first readings
scd30.read_measurement

# Actual read for processing
scd_buff = str(scd30.read_measurement())
parts = scd_buff.split(',')

#Extract Temperature & Relative Humidity values
Temperature = float(parts[1].replace("-", ""))
Humidity = float(parts[2].replace(")", ""))

# Find the Dewpoint from gathered temperature and humidity values
Dewpoint = 243.04 * (log(Humidity/100) + ((17.625*Temperature)/(243.04+Temperature))) / (17.625 - log(Humidity/100) - ((17.625*Temperature)/(243.04 + Temperature)))

# Adjust temperature value based on user offset
CalibTemperature = Temperature + temp_offset

# Find new humidity value based on calibrated temperature & the original dew point values
CalibHumidity = 100 * (exp((17.625*Dewpoint) / (243.04+Dewpoint)) / exp((17.625*CalibTemperature) / (243.04+CalibTemperature)))

# Round values to two decimal places (normalise the values)
CleanTemperature = str(int(round(CalibTemperature, 2)*100))
CleanHumidity = str(int(round(CalibHumidity, 2)*100))

# Determine if temperature is + or -
TemperatureCheck = float(parts[1])
if Temperature >= 0:
    z = 1
if Temperature < 0:
    z = 2

print('Temp & RH Data Gathered')



#------------SSD1306 Data Gathering & Cleaning

# Setup the buffer
buff = bytearray(255)

# Setup the variables
latitude = ""
longitude = ""
sealevel = ""
GPStime = ""
GPSFIX = False

def getGPS(gpsModule):  
               
    while True:
        global GPSFIX
        gpsModule.readline()
        buff = str(gpsModule.readline())
        parts = buff.split(',')

        # Make sure the data is valid
        if parts[0] == "b'$GPGGA" and len(parts) == 15 and "GP" not in parts[1:9]:    
            if parts[1] and parts[2] and parts[3] and parts[4] and parts[5] and parts[6] and parts [7] and parts[9]:
                print(buff)  

                # Extract and convert values as required
                latitude = convertToDegree(parts[2])
                if (parts[3] == 'S'):
                    latitude = '-'+latitude
                longitude = convertToDegree(parts[4])
                if (parts[5] == 'W'):
                    longitude = '-'+longitude
                sealevel = parts[9]
                GPStime = parts[1][0:2] + ":" + parts[1][2:4] + ":" + parts[1][4:6]
                SATs = parts[7]
                GPSarray = [latitude, longitude, sealevel, GPStime, SATs]
                print(GPSarray)
                GPSFIX = True
                return GPSarray
            wdt.feed()

        # Kill the loop if time runs out
        if time.time() > gps_end_time:
            GPSnull = []
            return GPSnull
        wdt.feed()
        sleep_ms(200)


def convertToDegree(RawDegrees):

    #Convert raw long & lat values to degrees
    RawAsFloat = float(RawDegrees)
    firstdigits = int(RawAsFloat/100) 
    nexttwodigits = RawAsFloat - float(firstdigits*100) 
    
    Converted = float(firstdigits + nexttwodigits/60.0)
    Converted = '{0:.6f}'.format(Converted) 
    return str(Converted)

print('Searching for GPS')


GPSarray = getGPS(gpsModule)

if GPSFIX == True:

    # Extract the values
    latitude = str(GPSarray[0])
    longitude = str(GPSarray[1])
    sealevel = float(GPSarray[2])
    GPStime = str(GPSarray[3])
    SATs = str(GPSarray[4])

    # Clean them up
    CleanLatitude = latitude.replace('.', '').replace('-', '')
    CleanLongitude = longitude.replace('.', '')
    CleanSeaLevel = str(int(round(sealevel, 1)*10))
    CleanGPSTime = GPStime.replace(':', '')
    CleanSATs = SATs # should already be clean.
else:
    # If the previous loop timed out infil null values
    GPSarray = [0, 0]
    CleanLatitude = "0"
    CleanLongitude = "0"
    CleanSeaLevel = "0"
    CleanGPSTime = "0"
    CleanGPSTime = "0"
    CleanSATs = "0"   


# Create an integer value to represent + or -
latitudeCheck = float(GPSarray[0])
if latitudeCheck >= 0:
    x = 1
if latitudeCheck < 0:
    x = 2

longitudeCheck = float(GPSarray[1])
if longitudeCheck >= 0:
    y = 1
if longitudeCheck < 0:
    y = 2

print ('GPS Data Gathered')



#------------SCD-30 CO2 Data Gathering & Cleaning


CO2data = False

while CO2data == False:
    # Wait for the SCD-30 to be ready
    while scd30.get_status_ready() != 1:
        sleep_ms(200)

    # Create a counter to allow the check to run a maximum of 2 times
    # Then obtain a CO2 reading and triple check it against a lower threshold to make sure its real (only an issue for sensors on a power timer)
    count = 0
    while count <= 2:
        scd_buff = str(scd30.read_measurement())
        parts = scd_buff.split(',')
        CO2 = float(parts[0].replace("(", ""))
        sleep_ms(2100) #Leave enough time to get a new reading each interval without overwhelming the sensor
        if CO2 >= 450:
            CO2data = True
            break
        else:
            count += 1
        wdt.feed()

    if count >= 2:
        CO2data = True
        break
    wdt.feed()
    sleep_ms(200)

# Prep the data for transmission
CleanCO2 = str(int(round(CO2 + co2_offset, 0)))

print('CO2 Data Gathered')



#------------Data Payload

# Add leading zeroes to ensure values are normalised for the payload
ZeroedCleanLatitude = "{:9d}".format(int(CleanLatitude))
ZeroedCleanLongitude = "{:9d}".format(int(CleanLongitude))
ZeroedCleanSeaLevel = "{:5d}".format(int(CleanSeaLevel))
ZeroedCleanCO2 = "{:4d}".format(int(CleanCO2))
ZeroedCleanTemperature = "{:5d}".format(int(CleanTemperature))
ZeroedCleanHumidity = "{:5d}".format(int(CleanHumidity))
ZeroedCleanGPSTime = "{:6d}".format(int(CleanGPSTime))
ZeroedCleanSATs = "{:2d}".format(int(CleanSATs))

# Assemble the payload
Payload = str(x) + str(y) + str(z) + str(ZeroedCleanLatitude) + str(ZeroedCleanLongitude) + str(ZeroedCleanSeaLevel) + str(ZeroedCleanCO2) + str(ZeroedCleanTemperature) + str(ZeroedCleanHumidity) + str(ZeroedCleanGPSTime) +str(ZeroedCleanSATs)

# Scrub the payload
FinalPayload = Payload.replace(" ", "0")
print('Final Payload :' + FinalPayload)

print('Payload Ready')



#------------LoRa-E5 Section

# Preset the gate variables
CONNECTED = False
SENT = False

# Receive response from the LoRa module
def receive_uart():
    rxData=bytes()
    while loraModule.any()>0:
        rxData += loraModule.read(1)
        sleep_ms(2)
    return rxData.decode('utf-8')

# Send command to the LoRa module
def send_AT(command):
    buffer = 'AT' + command + '\r\n'
    loraModule.write(buffer)
    sleep_ms(500)

# Join the LoRa Network
def join_the_things_network():
    
    global CONNECTED

    while CONNECTED == False:
        send_AT('+JOIN')
        data = receive_uart()
        if len(data) > 0: 
            print(data)
        if 'joined' in data or 'Joined already' in data:
            print('Network Joined')
            CONNECTED = True
        if time.time() > lora_end_time:
            print('Giving up on LoRa Connection...')
            break
        sleep_ms(1000)
        wdt.feed()

# Send message to the LoRa Network Server        
def send_message(message):

    global SENT
    send_AT('+MSG="' + message + '"')

    while SENT == False:
        data = receive_uart()
        if 'Done' in data or 'ERROR' in data:
            SENT = True
        if len(data) > 0: print(data)
        if time.time() > lora_end_time:
            print('Giving up on Sending Message...')
            break
        sleep_ms(1000)
        wdt.feed()



#------------LoRa Transmission

print("Attempting Connection...")

# Attempt to make a connection
while True:

    join_the_things_network()

    if CONNECTED == True:
        break
    if time.time() > lora_end_time:
        print('Giving up on LoRa Connection...')
        break
    wdt.feed()   

# Send the data payload if connected
if CONNECTED == True:
    send_message(FinalPayload)

# Short buffer to ensure message is sent
sleep_ms(2000)



#------------Maintenance & Shutdown

# Feed the watchdog
wdt.feed()

# Take out the garbage
gc.collect()
gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

print("Waiting for Ragnarok...")


# Used for always on sensors only
# Loop to end of the timer then restart or go to sleep
while True:

    if time.time() > end_time:
        print("End of cycle!")
        sleep_ms(500)
        machine.reset()
    wdt.feed()


# Used for timer based sensor only
# Trigger Pin 29 to tell the the Nano Power HAT timer to cut the power to the Pico
#GPIO_22.value(1)