#!/usr/bin/python
""" 
    mccli.py : CLI interface to MeschCore BLE companion app
"""
import os, sys
import time, datetime

from QNodeEditor import Node, Edge
from PyQt5.QtWidgets import QApplication
from PyQt5 import QtCore
from QNodeEditor import NodeEditorDialog, NodeEditor

class OutputNode(Node):
    code = 2
    def create(self) -> None:
        self.title='Outputs'

class InputNode(Node):
    code = 3
    def create(self) -> None:
        self.title='Inputs'

app = QApplication([])
editor = NodeEditor(allow_multiple_inputs=True)

outputs = OutputNode()
inputs = InputNode()

outputs.graphics.setPos(-200, 0)
inputs.graphics.setPos(200, 0)

editor.scene.add_nodes([outputs, inputs])

sensors = {}

def connected():
    edges = editor.scene.edges
    for e in edges:
        if e.end and e.start and not e.end.entry.name in sensors[e.start.entry.name]:
            print(f"connect {e.start.entry.name};{e.end.entry.name}")

def disconnected():
    print("disconnecting")
    edges = editor.scene.edges
    for s in sensors.items():
        pass

class WorkerThread(QtCore.QThread):
    def __init__(self):
        QtCore.QThread.__init__(self)
 
    def run(self):
        while True:
            line = sys.stdin.readline().rstrip('\n')
            if line.startswith("sensor "):
                name = line.split(" ", 1)[1]
                if not name in outputs:
                    sensors[name] = {}
                    outputs.add_label_output(name)
                    inputs.add_label_input(name)
                    inputs[name].socket.connected.connect(connected)
                    inputs[name].socket.disconnected.connect(disconnected)

            elif line.startswith("link "):
                names = line.split(" ", 1)[1].split(";")
                start = names[0]
                end = names[1]
                sensors[start][end]=True
                Edge(outputs[start], inputs[end])

def main(args):

    while True:
        line = sys.stdin.readline().rstrip('\n')
        if line.startswith("sensor "):
            name = line.split(" ", 1)[1]
            if not name in outputs:
                sensors[name] = {}
                outputs.add_label_output(name)
                inputs.add_label_input(name)
                inputs[name].socket.connected.connect(connected)
                inputs[name].socket.disconnected.connect(disconnected)

        elif line.startswith("link "):
            names = line.split(" ", 1)[1].split(";")
            start = names[0]
            end = names[1]
            sensors[start][end]=True
            Edge(outputs[start], inputs[end])

        elif line == "ready":
            break

    worker = WorkerThread()
    worker.start()

    editor.show()
    app.exec()

    edges = editor.scene.edges

    for e in edges:
        print(f"{e.start.entry.name} -> {e.end.entry.name}")

def cli():
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        # This prevents the KeyboardInterrupt traceback from being shown
        print("\nExited cleanly")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    cli()
