"""Materialize bounded native room metadata from the pinned field-only SOURCE map."""
import argparse
import json
from pathlib import Path

from native_room_revision import file_identity
from prepare_static_tilemap import map_driver,build_mask,read_mask
from run_room_transition_probe import validate_controls

KINDS={"spikesUp":"spike_up","spikesLeft":"spike_left","jumpThru":"jump_thru","spring":"spring","strawberry":"strawberry"}

def room_records(rooms):
    records=[]
    for room in rooms:
        a=room["attributes"]
        name=a["name"]
        if not name.startswith("lvl_") or not name[4:].isascii():
            raise ValueError("Unsupported room name")
        bounds=[a["x"],a["y"],a["width"],180 if a["height"]==184 else a["height"]]
        if any(type(value) is not int for value in bounds):
            raise ValueError("Room bounds require integer fields")
        if a.get("windPattern","None")!="None" or a.get("space",False) or a.get("underwater",False) or a.get("cameraOffsetX",0)!=0 or a.get("cameraOffsetY",0)!=0:
            raise ValueError("Unsupported room gameplay variant")
        if any(child.get("children") for child in room["children"] if child["name"]=="triggers"):
            raise ValueError("Unsupported room triggers")
        record={"name":name[4:],"bounds":bounds,"load_seed":sum(map(ord,name[4:])),"spawn":None,"objects":[]}
        entities=next(child["children"] for child in room["children"] if child["name"]=="entities")
        for entity in entities:
            kind=entity["name"];data=entity["attributes"]
            if entity.get("children") or data.get("nodes"):
                raise ValueError("Unsupported room entity nodes")
            position=[a["x"]+data["x"],a["y"]+data["y"]]
            if kind=="player":
                if record["spawn"] is not None: raise ValueError("Unsupported multiple room spawns")
                record["spawn"]=position
                continue
            if kind=="goldenBerry":
                if name!="lvl_1": raise ValueError("Unsupported golden berry room")
                continue
            if kind not in KINDS: raise ValueError("Unsupported room entity: "+kind)
            if data.get("type","default")!="default" or data.get("texture","default")!="default" or data.get("winged",False) or data.get("moon",False) or data.get("playerCanUse",True) is not True:
                raise ValueError("Unsupported room entity variant: "+kind)
            size=data.get("height",0) if kind=="spikesLeft" else data.get("width",0)
            values=[data["id"],*position,size]
            if any(type(value) is not int for value in values): raise ValueError("Room object requires integer fields")
            record["objects"].append([KINDS[kind],*values])
        if record["spawn"] is None: raise ValueError("Room needs a natural authored spawn")
        records.append(record)
    return records

def catalog_text(records):
    lines=["CROOM1",str(len(records))]
    for room in records:
        lines.append(" ".join(map(str,[room["name"],*room["bounds"],room["load_seed"],*room["spawn"],len(room["objects"])])))
        lines.extend(" ".join(map(str,values)) for values in room["objects"])
    return "\n".join(lines)+"\n"

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("profile","mask","controls","output"): parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/".audit") or args.output.exists(): parser.error("Output must be fresh and private")
    profile=json.loads((args.profile/"transition-profile.json").read_text())
    rooms_path=args.profile/"two-rooms.json"
    if file_identity(rooms_path)!=profile["generated"]["two-rooms.json"]: raise ValueError("Pinned SOURCE room fields changed")
    rooms=json.loads(rooms_path.read_text())
    if [room["attributes"]["name"] for room in rooms]!=["lvl_1","lvl_2"]: raise ValueError("Expected bounded room1/room2 profile")
    driver=map_driver({"children":[{"name":"levels","children":rooms}]})
    if build_mask(driver)!=read_mask(args.mask.read_text()): raise ValueError("Native mask differs from the supplied SOURCE two-room materialization")
    controls=json.loads(args.controls.read_text());validate_controls(controls)
    args.output.mkdir(parents=True)
    catalog=args.output/"catalog.txt";catalog.write_text(catalog_text(room_records(rooms)))
    inputs=[rooms_path,args.profile/"transition-profile.json",args.mask,args.controls,Path(__file__),root/"scripts/prepare_static_tilemap.py"]
    provenance={"schema":1,"scope":"Generated room metadata only, no outcome tape or native transition acceptance",
        "source_profile_historical_binding_unchanged":True,"excluded_authored_entities":{"lvl_1/goldenBerry":"The accepted SOURCE session does not instantiate this locked golden berry."},
        "mask_reused_in_place":str(args.mask.resolve()),"controls_reused_in_place":str(args.controls.resolve()),
        "inputs":{str(path.resolve()):file_identity(path) for path in inputs},"files":{"catalog.txt":file_identity(catalog)}}
    (args.output/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    print(str(catalog.resolve()))

if __name__=="__main__": main()
