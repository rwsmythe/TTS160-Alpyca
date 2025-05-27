# TTS160 Alpaca Driver
## Introduction
This driver is a python-based alpaca driver for the TTS-160 mount.  It will have the same baseline functionality as the old ASCOM driver with the planned expansion of future capabilities.

## Multiplatform
Because this is written in python, it naturally lends itself to being multiplatform, so the driver will now be able to be used natively on any platform that has the required python libraries, and with any applications that support Alpaca.

## Differences from the original ASCOM driver
-For windows users, this driver will have to be manually started.  There is an ASCOM capability to subsequently generate a local driver which will then act as a normal ASCOM driver and not need to be manually started.\n
-The driver will natively allow for connection from remote machines, assuming the OS allows access on the required ports (the normal ALPACA ports are used).  The machine the driver runs on must be physically connected to the mount.\n
-There is no requirement for ASCOM to be installed on the machine running the driver.  The driver runs a stand-alone webserver that handles the requests and communicates directly with the mount.

## Firmware Compatibility
This driver is intended to be compatible with firmware from **356** onward.

## GUI - Planned
There will be a GUI developed to handle driver settings (similar to the ASCOM driver setup window).  The intent will be for this GUI to provide insight into the current state of the mount as well.  This will enable the development of further advanced features for users to leverage.

## Distribution Packages
The intent is for this driver to have a distribution package similar to the one for ASCOM driver.  Ideally, this will include for deployment on Linux/Raspbian and Mac OSes as well.
