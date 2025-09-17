#!/usr/bin/python
""" 
    MCSerialPatchBay: graphical patchbay for MCSerialManager
"""
import os, sys
import time, datetime
import subprocess
import traceback

from QNodeEditor import Node, Edge, Entry
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

streamout = sys.stdout
streamin = sys.stdin

def printout(str):
    streamout.write(f"{str}\n")
    streamout.flush()

def edges_dict():
    new_edges = {}
    for s in sensors.items():
        new_edges[s[0]] = {}
    for e in editor.scene.edges:
        if e.start and e.end:
            if e.start.entry.entry_type == Entry.TYPE_OUTPUT:
                new_edges[e.start.entry.name][e.end.entry.name]=True
            else:
                new_edges[e.end.entry.name][e.start.entry.name]=True
    return new_edges
    
def connected():
    edges = edges_dict()
    for s in edges.items():
        for o in dict(s[1]).items():
            if not o[0] in sensors[s[0]]:
                printout(f"connect {s[0]};{o[0]}")
                sensors[s[0]][o[0]] = True

def disconnected():
    edges = edges_dict()
    for s in sensors.items():
        for o in dict(s[1]).items():
            if not o[0] in edges[s[0]]:
                printout(f"disconnect {s[0]};{o[0]}") 
                del s[1][o[0]]

def eval_line(line):
    if line.startswith("sensor ") or line.startswith("s "):
        name = line.split(" ", 1)[1]
        if not name in outputs:
            sensors[name] = {}
            outputs.add_label_output(name)
            inputs.add_label_input(name)
            inputs[name].socket.connected.connect(connected)
            inputs[name].socket.disconnected.connect(disconnected)
            outputs[name].socket.connected.connect(connected)
            outputs[name].socket.disconnected.connect(disconnected)

    elif line.startswith("link ") or line.startswith("l "):
        names = line.split(" ", 1)[1].split(";")
        start = names[0]
        end = names[1]
        if not end in sensors[start]:
            sensors[start][end]=True
            Edge(outputs[start], inputs[end])

class WorkerThread(QtCore.QThread):
    def __init__(self):
        QtCore.QThread.__init__(self)
 
    def run(self):
        for l in streamin:
            eval_line(l.rstrip('\n'))

def main(args):
    global streamin, streamout

    if len(args) > 0:
        print("starting process")
        p = subprocess.Popen(args, 
                #bufsize=1,
                close_fds=True,
                universal_newlines=True, 
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE)
        #p = os.popen(args[0], 'r')
        streamin = p.stdout
        streamout = p.stdin

    print("init loop")
    for l in streamin:
        line = l.rstrip('\n')
        if line == "r" or line == "ready":
            break # end of init phase
        eval_line(line)

    print("starting")
    worker = WorkerThread()
    worker.start()

    editor.show()
    app.exec()

    if p.poll() is None:
        printout("q")

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
