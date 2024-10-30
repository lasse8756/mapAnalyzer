# Input: Name, ROM, RAM
import json, argparse

# read name, rom, ram
parser = argparse.ArgumentParser("addDevice")
parser.add_argument("name", help="name of the device", type=str)
parser.add_argument("rom", help="available rom (kB)", type=int)
parser.add_argument("ram", help="available ram (kB)", type=int)
args = parser.parse_args()

with open("cfg/devices.json", "r") as f:
    config = json.load(f)

new_devices = {
    args.name: {"rom": args.rom, "ram": args.ram},
}

config["devices"].update(new_devices)

with open("cfg/devices.json", "w") as json_file:
    json.dump(config, json_file, indent=4)
