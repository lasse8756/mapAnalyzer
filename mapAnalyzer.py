from enum import Enum
from pathlib import Path
import argparse
import sqlite3
import re
import json
import configparser

# regex pattern to match relevant lines in ENTRY LIST
regex_entry = re.compile(
    r"(?P<module>\S+)\s+(?P<ro_code>[\d\']+)?\s+(?P<ro_data>[\d\']+)?\s+(?P<rw_data>[\d\']+)?"
)


class CodeModule:
    __slots__ = ["name", "ro_code", "ro_data", "rw_data"]

    def __init__(self, name, ro_code, ro_data, rw_data):
        self.name = name
        self.ro_code = ro_code
        self.ro_data = ro_data
        self.rw_data = rw_data


class MapSections(Enum):
    INIT = 0
    MODULE_SUMMARY = 1
    ENTRY_LIST = 2


class MemorySections(Enum):
    RO_CODE = 0
    RO_DATA = 1
    RW_DATA = 2
    END = 3


# globals
map_section = MapSections.INIT
memory_section = MemorySections.RO_CODE
code_modules = []
total_ro_code = 0
total_ro_data = 0
total_rw_data = 0


def calcPercentage(n, d):  # prevents division by 0
    return n / d * 100 if d else 0


def extractNumber(line: str) -> int:
    match = re.search(r"(\d{1,3}(?:'\d{3})*)", line)  # Regex to get number from line
    number = 0
    if match:
        # Replace apostrophes with nothing to get a clean number
        number_str = match.group(1).replace("'", "")
        number = int(number_str)
    return number


# line processing state machine #TODO: extend functionality?
def processLine(line: str):
    global map_section, memory_section, code_modules, total_ro_code, total_ro_data, total_rw_data

    match map_section:
        case MapSections.INIT:
            if "*** MODULE SUMMARY" in line:
                map_section = MapSections.MODULE_SUMMARY
            return
        case MapSections.MODULE_SUMMARY:
            if "*** ENTRY LIST" in line:
                map_section = MapSections.ENTRY_LIST
            else:  # process module data
                match = regex_entry.search(line)
                if match:
                    module = match.group("module")
                    if module.endswith(".o") or module.endswith(
                        ".obj"
                    ):  # for module we only care about anything ending with .o or obj
                        ro_code = match.group("ro_code") or "0"
                        ro_data = match.group("ro_data") or "0"
                        rw_data = match.group("rw_data") or "0"

                        # Clean the numeric fields (replace ' with nothing and convert to int)
                        ro_code = int(ro_code.replace("'", ""))
                        ro_data = int(ro_data.replace("'", ""))
                        rw_data = int(rw_data.replace("'", ""))

                        code_modules.append(
                            CodeModule(module, ro_code, ro_data, rw_data)
                        )
            return
        case MapSections.ENTRY_LIST:
            match memory_section:
                case MemorySections.RO_CODE:
                    if line.endswith(" memory") or line.endswith("absolute)"):
                        # found the beginning of the memory usage data section
                        total_ro_code = extractNumber(line)
                        memory_section = MemorySections.RO_DATA
                        return
                # these will always be exactly one line after each other
                case MemorySections.RO_DATA:
                    total_ro_data = extractNumber(line)
                    memory_section = MemorySections.RW_DATA
                case MemorySections.RW_DATA:
                    total_rw_data = extractNumber(line)
                    memory_section = MemorySections.END
                case _:
                    return
        case _:
            return


# get command line arguments, if not provided use defaults from config.ini instead
config = configparser.ConfigParser()
config.read("cfg/config.ini")

parser = argparse.ArgumentParser("iarMapAnalyzer")
parser.add_argument(
    "-map",
    help="path to the .map file (input)",
    default=config["Parameters"]["InputFolder"] + "/" + config["Parameters"]["MapName"],
    type=str,
    required=False,
)
parser.add_argument(
    "-device",
    help="device config to read from devices.json",
    type=str,
    default=config["Parameters"]["Device"],
    required=False,
)
args = parser.parse_args()

# process map file #TODO: other sections besides 'MODULE SUMMARY'? not sure what to do with them
f = open(args.map)
line = f.readline()
while line:
    line = line.rstrip()
    processLine(line)
    line = f.readline()
f.close()

# make sure folder and db file exist
output_folder = config["Parameters"]["OutputFolder"]
db_path = output_folder + "/" + config["Parameters"]["DBName"]
Path(output_folder).mkdir(parents=True, exist_ok=True)

# fill db with entries
db_connection = sqlite3.connect(db_path)
db_cursor = db_connection.cursor()
db_cursor.execute("DROP TABLE IF EXISTS modules")
db_cursor.execute(
    """
    CREATE TABLE modules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ro_code INTEGER NOT NULL,
        ro_data INTEGER NOT NULL,
        rw_data INTEGER NOT NULL
    )
"""
)

for CodeModule in code_modules:
    db_cursor.execute(
        """
        INSERT INTO modules (name, ro_code, ro_data, rw_data)
        VALUES (?, ?, ?, ?)
    """,
        (
            CodeModule.name,
            CodeModule.ro_code,
            CodeModule.ro_data,
            CodeModule.rw_data,
        ),
    )

db_connection.commit()
db_connection.close()

# get available rom/ram from config
with open("cfg/devices.json", "r") as f:
    config = json.load(f)

available_rom_b = 0
available_ram_b = 0
KB_TO_B_FACTOR = 1014
device = config["devices"].get(args.device)
if device:
    available_rom_b = device.get("rom") * KB_TO_B_FACTOR
    available_ram_b = device.get("ram") * KB_TO_B_FACTOR

# command line output
total_rom_used = total_ro_code + total_ro_data
rom_percentage = calcPercentage(total_rom_used, available_rom_b)
ram_percentage = calcPercentage(total_rw_data, available_ram_b)
# TODO: do something nicer with this?
print("detailed memory usage data has written to " + db_path)
print("--------------------------------------------------")
print("readonly code memory used: " + str(total_ro_code) + " bytes")
print("readonly data memory used: " + str(total_ro_data) + " bytes")
print("total readonly memory used: " + str(total_rom_used) + " bytes")
print("--------------------------------------------------")
print("readwrite data memory used: " + str(total_rw_data) + " bytes")
print("--------------------------------------------------")
print("percent rom used: " + str(round(rom_percentage, 2)) + "%")
print("percent ram used: " + str(round(ram_percentage, 2)) + "%")


# TODO: do something with data?
