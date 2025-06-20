﻿# TTS160 Alpaca Driver
## Introduction
This driver is a python-based alpaca driver for the TTS-160 mount.  It will have the same baseline functionality as the old ASCOM driver with the planned expansion of future capabilities.

## Multiplatform
Because this is written in python, it naturally lends itself to being multiplatform, so the driver will now be able to be used natively on any platform that has the required python libraries, and with any applications that support Alpaca.

## Differences from the original ASCOM driver
1. For windows users, this driver will have to be manually started.  There is an ASCOM capability to subsequently generate a local driver which will then act as a normal ASCOM driver and not need to be manually started.
2. The driver will natively allow for connection from remote machines, assuming the OS allows access on the required ports.  The machine the driver runs on must be physically connected to the mount.
3. There is no requirement for ASCOM to be installed on the machine running the driver.  The driver runs a stand-alone webserver that handles the requests and communicates directly with the mount.

## Firmware Compatibility
This driver is intended to be compatible with firmware from **356** onward.

## GUI - Planned
There will be a GUI developed to handle driver settings (similar to the ASCOM driver setup window).  The intent will be for this GUI to provide insight into the current state of the mount as well.  This will enable the development of further advanced features for users to leverage.
* Initial GUI created and is working -> it can start and stop the server
* Next step: show and edit configurations (config.toml, TTS160config.toml)

## Distribution Packages
The intent is for this driver to have a distribution package similar to the one for ASCOM driver.  Ideally, this will include for deployment on Linux/Raspbian and Mac OSes as well.
* Initial testing with pyinstaller a success, using tts160_pyinstaller as script generator
* Need to create an actual install .exe file, probably using Inno Setup like the ASCOM driver
* Need to figure out how to make macos and linux containers to create macos and linux distributables

## TODO before conform testing
* ~~Fix connect/disconnect logic so you can reconnect multiple times (ready for initial verification testing)~~
* ~~Verify multiple connects and disconnects from multiple clients (Sharpcap, NINA, phd, etc...) do not break connect/disconnect logic (ready for initial verification testing)~~
* ~~Continue converting methods - SlewToxxx should be the last big ones.  Also need the syncs, now that I think of it~~
* ~~Have abort slew bypass settling time: set _goto_in_progress to False before sending the abort command~~
* ~~Implement EquatorialSystem in applicable functions.  Likely make two alt-az <-> ra-dec conversion functions that will choose the correct epoch based on the mount so that we don't need to check in each and every function.  Functions...SlewToAltAzAsync, SlewToCoordinatesAsync, all of the Syncs, FindHome, any others?~~
* ~~Add an internal get park variable status command for driver awareness, should be read on initial connect.  Need to figure out a good method for periodic update of mount status (epoch, location, park settings, etc...) for later inclusion in the gui~~
* ~~Add log entries to support debugging, add function documentation (see good todos)~~
* Conform testing complete, Alpaca protocol testing complete, discovery testing complete!

## Good TODOs
* ~~Run existing methods through Claude to ensure pythonic, best practices, documented, etc...~~

## Known bugs
* ~~NINA does not seem to like how time is passed, it fails the mount/computer difference check~~ <-- Fixed by changing "+00:00" for UTCDate timezone to "Z"

## Headscratchers
* ~~How to deal with EquPulseGuide timing, particular when some programs (metaguide?) expect the mount to indicate pulse-guiding for the defined time?  Possibly spin off a monitor thread to handle that specific case.  A ns and ew for the ordered duration to simulate ra and dec motor motion, allowing for ra and eq orders to be executed?  How will that interface with the hardware?~~
