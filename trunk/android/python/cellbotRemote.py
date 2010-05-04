# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#
# See http://www.cellbots.com for more information

__license__ = 'Apache License, Version 2.0'

import android
import os
import time
import xmpp
import ConfigParser
import math
import robot
from threading import Thread

# Establish an XMPP connection
def commandByXMPP():
  global xmppClient
  jid = xmpp.protocol.JID(xmppUsername)
  xmppClient = xmpp.Client(jid.getDomain(), debug=[])
  xmppClient.connect(server=(xmppServer, xmppPort))
  try:
    xmppClient.RegisterHandler('message', XMPP_message_cb)
  except:
    exitCellbot('XMPP error. You sure the phone has an internet connection?')
  if not xmppClient:
    exitCellbot('XMPP Connection failed!')
    return
  auth = xmppClient.auth(jid.getNode(), xmppPassword, 'botty')
  if not auth:
    exitCellbot('XMPP Authentication failed!')
    return
  xmppClient.sendInitPresence()
  print "XMPP username for the robot is:\n" + xmppUsername
  runRemoteControl()


# Handle XMPP messages coming from commandByXMPP
def XMPP_message_cb(session, message):
  jid = xmpp.protocol.JID(message.getFrom())
  global operator
  operator = jid.getNode() + '@' + jid.getDomain()
  command = message.getBody()
  print str(command)
      
# Listen for incoming Bluetooth resonses. If this thread stops working, try rebooting. 
class bluetoothReader(Thread):
  def __init__ (self):
    Thread.__init__(self)
 
  def run(self):
    while True:
      if not droid.bluetoothReady():
        time.sleep(0.05)
        continue
        result += droid.bluetoothRead()
        if '\n' in result:
          npos = result.find('\n')
          yield result[:npos]
          result = result[npos+1:]
          print result

# Initialize Bluetooth outbound if configured for it
def initializeBluetooth():
  droid.toggleBluetoothState(True)
  droid.bluetoothConnect("00001101-0000-1000-8000-00805F9B34FB") #this is a magic UUID for serial BT devices
  droid.makeToast("Initializing Bluetooth connection")
  time.sleep(4)

# Send command out of the device over BlueTooth or XMPP
def commandOut(msg):
  if outputMethod == "outputBluetooth":
    droid.bluetoothWrite(msg + '\r\n')
  else:
    global previousMsg
    global lastMsgTime
    # Don't send the same message repeatedly unless 1 second has passed
    if msg != previousMsg or (time.time() > lastMsgTime + 1000):
      xmppClient.send(xmpp.Message(xmppRobotUsername, msg))
    previousMsg=msg
    lastMsgTime = time.time()
  
def runRemoteControl():
  droid.startSensing()
  time.sleep(1.0) # give the sensors a chance to start up
  while 1:
    sensor_result = droid.readSensors()
    pitch=int(sensor_result.result['pitch'])
    roll=int(sensor_result.result['roll'])

    # Assumes the phone is held in portrait orientation and that
    # people naturally hold the phone slightly pitched forward.
    # Translate and scale a bit to keep the values mostly in -150:20
    # with 50 degrees forward and back multiple by 2 for a full range -100:100
    if pitch in range(-20, -10):
      speed = 100
      droid.vibrate((pitch + 20) * 10)
      print "Too far forward"
    elif pitch in range(-70, -20):
      speed = (pitch + 70) * 2
    elif pitch in range(-100, -70):
      speed = 0
      print "Steady"
    elif pitch in range(-150, -100):
      speed = (pitch + 100) * 2
    elif pitch in range(-170, -150):
      speed = -100
      droid.vibrate(((pitch + 150) *-1) * 10)
      print "Too far backward"
    else:
      # We set speed to zero and fake roll to zero so laying the phone flat stops bot
      speed = 0
      roll =0
      print "Stopping bot"

    # Some empirical values, and also a gutter (dead spot) in the middle.
    if roll > 50:
      direction = -100
      droid.vibrate((roll -50) * 10)
      print "Too far left"
    elif roll < -50:
      direction = 100
      droid.vibrate(((roll *-1) -50) * 10)
      print "too far right"
    elif roll in range(-3,3):
      direction = 0
    else:
      direction = roll * 2

    # Reverse turning when going backwards
    if speed < 0:
      direction = direction * -1

    # Clamp speed and direction between -100 and 100 just in case the above let's something slip
    speed = max(min(speed, 100), -100)
    direction = max(min(direction, 100), -100)

    # Apply acceleration scaling factor since linear use of the accelerometer goes to fast with minor tilts
    scaledSpeed = math.pow(abs(speed) / 100.00, speedScaleFactor)
    speed = math.copysign(scaledSpeed, speed) * 100.00
    scaledDirection = math.pow(abs(direction) / 100.00, directionScaleFactor)
    direction = math.copysign(scaledDirection, direction) * 100.00

    # Okay, speed and direction are now both in the range of -100:100.
    # Speed=100 means to move forward at full speed.  direction=100 means
    # to turn right as much as possible.

    # Treat direction as the X axis, and speed as the Y axis.
    # If we're driving a differential-drive robot (each wheel moving forward
    # or back), then consider the left wheel as the X axis and the right
    # wheel as Y.
    # If we do that, then we can translate [speed,direction] into [left,right]
    # by rotating by -45 degrees.
    # See the writeup at [INSERT URL HERE]

    # This actually rotates by 45 degrees and scales by 1.414, so that full
    # forward = [100,100]
    right = speed - direction
    left = speed + direction

    # But now that we've scaled, asking for full forward + full right turn
    # means the motors need to go to 141.  If we're asking for > 100, scale
    # back without changing the proportion of forward/turning
    if abs(left) > 100 or abs(right) > 100:
      scale = 1.0
      # if left is bigger, use it to get the scaling amount
      if abs(left) > abs(right):
        scale = 100.0 / left
      else:
        scale = 100.0 / right
      
      left = int(scale * left)
      right = int(scale * right)

    print pitch, roll, speed, direction

    command = "w %d %d" % (left, right)
    #print command
    commandOut(command)

    time.sleep(0.10)

# Get configurable options from the ini file, prompt user if they aren't there, and save if needed
def getConfigFileValue(config, section, option, title, valueList, saveToFile):
  # Check if option exists in the file
  if config.has_option(section, option):
    values = config.get(section, option)
    values = values.split(',')
    # Prompt the user to pick an option if the file specified more than one option
    if len(values) > 1:
      setting = robot.pickFromList(title, values)
    else:
      setting = values[0]
  else:
    setting = ''
  # Deal with blank or missing values by prompting user
  if not setting or not config.has_option(section, option):
    # Provide an empty text prompt if no list of values provided
    if not valueList:
      setting = robot.getInput(title).result
    # Let the user pick from a list of values
    else:
      setting = robot.pickFromList(title, valueList)
    if saveToFile:
      config.set(section, option, setting)
      with open(configFilePath, 'wb') as configfile:
        config.write(configfile)
  return setting

# Setup the config file for reading and be sure we have a phone type set
config = ConfigParser.ConfigParser()
configFilePath = "/sdcard/ase/scripts/cellbotRemoteConfig.ini"
config.read(configFilePath)
if config.has_option("basics", "phoneType"):
  phoneType = config.get("basics", "phoneType")
else:
  phoneType = "android"
  config.set("basics", "phoneType", phoneType)
robot = robot.Robot(phoneType)

#Non-configurable settings
droid = android.Android()
previousMsg = ""
lastMsgTime = time.time()

# List of config values to get from file or prompt user for
outputMethod = getConfigFileValue(config, "control", "outputMethod", "Select Output Method", ['outputXMPP', 'outputBluetooth'], True)
xmppUsername = getConfigFileValue(config, "xmpp", "username", "Chat username", '', True)
xmppPassword = getConfigFileValue(config, "xmpp", "password", "Chat password", '', False)
xmppRobotUsername = getConfigFileValue(config, "xmpp", "robotUsername", "Robot username", '', True)
xmppServer = config.get("xmpp", "server")
xmppPort = config.getint("xmpp", "port")
speedScaleFactor = 1.5
directionScaleFactor = 2.0

# The main loop that fires up a telnet socket and processes inputs
def main():
  print "Lay the phone flat to pause the program.\n"
  if outputMethod == "outputBluetooth":
    initializeBluetooth()
    #readerThread = bluetoothReader()
  else:
    commandByXMPP()
  #readerThread.start()
  droid.makeToast("Move the phone to control the robot")
  runRemoteControl()

if __name__ == '__main__':
    main()