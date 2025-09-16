#!/usr/bin/python
""" 
    mccli.py : CLI interface to MeschCore BLE companion app
"""
import asyncio
import os, sys
import time, datetime
import getopt, json, shlex, re
import logging
import requests
from bleak import BleakScanner, BleakClient
import serial.tools.list_ports
from pathlib import Path
import traceback
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import radiolist_dialog

from meshcore import MeshCore, EventType, logger

from QNodeEditor import Node, Edge
from PyQt5.QtWidgets import QApplication
from QNodeEditor import NodeEditorDialog, NodeEditor

# Version
VERSION = "v0.1"

# default ble address is stored in a config file
MCCLI_CONFIG_DIR = str(Path.home()) + "/.config/meshcore/"
MCCLI_ADDRESS = MCCLI_CONFIG_DIR + "default_address"
MCCLI_HISTORY_FILE = MCCLI_CONFIG_DIR + "history"
MCCLI_INIT_SCRIPT = MCCLI_CONFIG_DIR + "init"

# Fallback address if config file not found
# if None or "" then a scan is performed
ADDRESS = ""
JSON = False

PS = None
CS = None

def version():
    print (f"MeshCore Serial PatchBay version: {VERSION}")

def usage () :
    """ Prints some help """
    version()

class OutputNode(Node):
    code = 2
    def create(self) -> None:
        self.title='Outputs'

class InputNode(Node):
    code = 3
    def create(self) -> None:
        self.title='Inputs'


async def main(argv):
    """ Do the job """
    json_output = JSON
    debug = False
    address = ADDRESS
    device = None
    port = 5000
    hostname = None
    serial_port = None
    baudrate = 115200
    timeout = 2
    # If there is an address in config file, use it by default
    # unless an arg is explicitely given
    if os.path.exists(MCCLI_ADDRESS) :
        with open(MCCLI_ADDRESS, encoding="utf-8") as f :
            address = f.readline().strip()

    opts, args = getopt.getopt(argv, "a:d:s:ht:p:b:jDhvSlT:")
    for opt, arg in opts :
        match opt:
            case "-d" : # name specified on cmdline
                address = arg
            case "-a" : # address specified on cmdline
                address = arg
            case "-s" : # serial port
                serial_port = arg
            case "-b" :
                baudrate = int(arg)
            case "-t" :
                hostname = arg
            case "-p" :
                port = int(arg)
            case "-j" :
                json_output=True
                handle_message.json_output=True
            case "-D" :
                debug=True
            case "-h" :
                usage()
                return
            case "-T" :
                timeout = float(arg)
            case "-v":
                version()
                return
            case "-l" :
                print("BLE devices:")
                devices = await BleakScanner.discover(timeout=timeout)
                if len(devices) == 0:
                    print(" No ble device found")
                for d in devices :
                    if not d.name is None and d.name.startswith("MeshCore-"):
                        print(f" {d.address}  {d.name}")
                print("\nSerial ports:")
                ports = serial.tools.list_ports.comports()
                for port, desc, hwid in sorted(ports):
                    print(f" {port:<18} {desc} [{hwid}]")
                return
            case "-S" :
                devices = await BleakScanner.discover(timeout=timeout)
                choices = []
                for d in devices:
                    if not d.name is None and d.name.startswith("MeshCore-"):
                        choices.append(({"type":"ble","device":d}, f"{d.address:<22} {d.name}"))

                ports = serial.tools.list_ports.comports()
                for port, desc, hwid in sorted(ports):
                    choices.append(({"type":"serial","port":port}, f"{port:<22} {desc}"))
                if len(choices) == 0:
                    logger.error("No device found, exiting")
                    return

                result = await radiolist_dialog(
                    title="MeshCore-cli device selector",
                    text="Choose the device to connect to :",
                    values=choices
                ).run_async()

                if result is None:
                    logger.info("No choice made, exiting")
                    return

                if result["type"] == "ble":
                    device = result["device"]
                elif result["type"] == "serial":
                    serial_port = result["port"]
                else:
                    logger.error("Invalid choice")
                    return
                    
    if (debug==True):
        logger.setLevel(logging.DEBUG)
    elif (json_output) :
        logger.setLevel(logging.ERROR)

    mc = None
    if not hostname is None : # connect via tcp
        mc = await MeshCore.create_tcp(host=hostname, port=port, debug=debug, only_error=json_output)
    elif not serial_port is None : # connect via serial port
        mc = await MeshCore.create_serial(port=serial_port, baudrate=baudrate, debug=debug, only_error=json_output)
    else : #connect via ble
        client = None
        if device or address and len(address.split(":")) == 6 :
            pass
        elif address and len(address) == 36 and len(address.split("-")) == 5:
            client = BleakClient(address) # mac uses uuid, we'll pass a client
        else:
            logger.info(f"Scanning BLE for device matching {address}")
            devices = await BleakScanner.discover(timeout=timeout)
            found = False
            for d in devices:
                if not d.name is None and d.name.startswith("MeshCore-") and\
                        (address is None or address in d.name) :
                    address=d.address
                    device=d
                    logger.info(f"Found device {d.name} {d.address}")
                    found = True
                    break
                elif d.address == address : # on a mac, address is an uuid
                    device = d
                    logger.info(f"Found device {d.name} {d.address}")
                    found = True
                    break

            if not found :
                logger.info(f"Couldn't find device {address}")
                return

        mc = await MeshCore.create_ble(address=address, device=device, client=client, debug=debug, only_error=json_output)

        # Store device address in configuration
        if os.path.isdir(MCCLI_CONFIG_DIR) :
            with open(MCCLI_ADDRESS, "w", encoding="utf-8") as f :
                f.write(address)


    res = await mc.commands.send_device_query()
    if res.type == EventType.ERROR :
        logger.error(f"Error while querying device: {res}")
        return

    if (json_output) :
        logger.setLevel(logging.ERROR)
    else :
        if res.payload["fw ver"] > 2 :
            logger.info(f"Connected to {mc.self_info['name']} running on a {res.payload['ver']} fw.")
        else :
            logger.info(f"Connected to {mc.self_info['name']}.")

    await mc.ensure_contacts()

    sensors = []

    for ct in mc.contacts.items():
        c = ct[1]
        
        if (c["type"] == 4) :
            s = {}
            s["name"]=c["adv_name"]
            s["key"]=c["public_key"]
            sensors.append(s)

    # get acls from reachable nodes
    for s in list(sensors):
        print(f"requesting acl from {s['name']}")
        a = await mc.commands.req_acl_sync(s["key"])
        if a is None: # could not get data
            print(f"{s['name']} is not available")
            sensors.remove(s)
        else:
            s["acl"] = a

    # compute links
    for s in sensors:
        print(f"Sensor: {s['name']} : ")
        s["out"] = []
        for o in s["acl"]:
            for ss in sensors:
                if o["key"] == ss["key"][0:12] and o["perm"] & 0xc0 == 0xc0:
                    s["out"].append(ss)
                    print(f" -> {ss['name']}")

    app = QApplication([])
    #dialog = NodeEditorDialog(allow_multiple_inputs=True)
    #editor = dialog.editor
    editor = NodeEditor(allow_multiple_inputs=True)

    outputs = OutputNode()
    outputs.graphics.setPos(-200, 0)
    inputs = InputNode()
    inputs.graphics.setPos(200, 0)

    for s in sensors:
        outputs.add_label_output(s['name'])
        inputs.add_label_input(s['name'])

    editor.scene.add_nodes([outputs, inputs])

#    if dialog.exec():
#        print(dialog.result)

    for o in sensors:
        for i in o['out']:
            Edge(outputs[o['name']], inputs[i['name']])

    editor.show()
    app.exec()

    edges = editor.scene.edges
    edge_dict = {}
    for s in sensors:
        edge_dict[s["name"]] = {}
        edge_dict[s["name"]]["out"] = []

    for e in edges:
        edge_dict[e.start.entry.name]["out"].append(e.end.entry.name)
        print(f"{e.start.entry.name} -> {e.end.entry.name}")

    for s in sensors:
        for ss in sensors:
            if ss in s["out"] and not ss['name'] in edge_dict[s["name"]]["out"]:
                print(f"{s['name']} has been disconnected from {ss['name']}")
                await mc.commands.send_cmd(s['key'], f"setperm {ss['key']} 3")
            if not ss in s["out"] and ss['name'] in edge_dict[s['name']]['out']:
                print(f"{s['name']} has been connected to {ss['name']}")
                await mc.commands.send_cmd(s['key'], f"setperm {ss['key']} 195")
                # we should also set the reciprocal path ...
            
def cli():
    try:
        asyncio.run(main(sys.argv[1:]))
    except KeyboardInterrupt:
        # This prevents the KeyboardInterrupt traceback from being shown
        print("\nExited cleanly")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    cli()
