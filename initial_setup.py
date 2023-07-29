# This script is based off the Core Electronics starter code and Getting Started Guide by seeedstudio:
# https://wiki.seeedstudio.com/LoRa-E5_STM32WLE5JC_Module/#getting-started


from machine import UART, Pin
from utime import sleep_ms



#------------Serial Connection

loraModule = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))



#------------Configuring the LoRaWAN Modem (LoRa-E5 Module)

#Paste your generated key from the things stack here
app_key = '123123123123123123123123123'

# Regional LoRaWAN settings. You may need to modify these depending on your region.
# If you are using AU915
band='AU915'
channels='8-15'

# If you are using US915
# band='US915'
# channels='8-15'

# If you are using EU868
# band='EU868'
# channels='0-2'



#------------LoRa-E5 Module EUI Information

# Leave blank, the script will output these variable in Shell
# When they appear copy them in to your application setup on the things stack
join_EUI = None
device_EUI = None



#------------LoRa-E5 Section

CONNECTED = False
SENT = False

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


# Gathers the Device EUI & Join EUI from the device
def get_eui_from_radio():
    send_AT('+ID=DevEui')
    data = receive_uart()
    device_EUI = data.split()[2]

    send_AT('+ID=AppEui')
    data = receive_uart()
    join_EUI = data.split()[2]

    print(f'JoinEUI: {join_EUI}\n DevEUI: {device_EUI}')


# Saves the app key to the LoRa-E5 Module    
def set_app_key(app_key):

    send_AT('+KEY=APPKEY,"' + app_key + '"')
    receive_uart()
    print(f' AppKey: {app_key}\n')


# Saves the regional settings to the LoRa-E5 Module
def configure_regional_settings(band=None, DR='0', channels=None):
    
    send_AT('+DR=' + band)
    send_AT('+DR=' + DR)
    send_AT('+CH=NUM,' + channels)
    send_AT('+MODE=LWOTAA')
    receive_uart()
    
    send_AT('+DR')
    data = receive_uart()
    print(data)


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
        sleep_ms(1000)

       
# Send message to the LoRa Network Server        
def send_message(message):

    global SENT
    send_AT('+MSG="' + message + '"')

    while SENT == False:
        data = receive_uart()
        if 'Done' in data or 'ERROR' in data:
            print('Payload Sent')
            SENT = True
        if len(data) > 0: print(data)
        sleep_ms(1000)



#------------Dummy Payload

# Dummy data to test the payload decoder
FinalPayload = '211035000000138540000006400550021900491607333603'
#Should read as
#CO2: 550
#LAT: 35.000000
#LON: 138.540000
#Latitude Sign: 1
# RH: 49
# SATS: 3
# SEA: 64
# TEMP: 21.9
# TIME: 73336
# Temperature_Sign: 1
# True_LAT: -35.000000



#------------LoRa Setup & Test Connection


get_eui_from_radio()

set_app_key(app_key)

configure_regional_settings(band=band, DR='0', channels=channels)

join_the_things_network()

if CONNECTED == True:
    send_message(FinalPayload)

print("All Done!")
