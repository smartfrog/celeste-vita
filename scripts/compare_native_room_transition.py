"""Explicit semantic projection of the immutable SOURCE recording and actual native session observations."""
import argparse
import hashlib
import json
from pathlib import Path

from compare_room_transition_contract import same,validate,require
from prepare_native_transition_fixture import room_records

FIELDS=("room","bounds","previousBounds","position","center","upProbe","speed","remainder","state","previousState","Locked","Dead",
        "Dashes","Stamina","AutoJump","AutoJumpTimer","varJumpTimer","jumpGraceTimer","wallSlideTimer","forceMoveXTimer","onGround","groundQuery",
        "camera","Transitioning","NextTransitionDuration","animation","animationFrame","spriteScale","hairNodes","respawn","TimeActive","RawTimeActive",
        "FrameCounter","FreezeTimer","TimeRate","TimeRateB","sessionTime","saveTime","roomDeaths","sessionDeaths","saveDeaths","sessionDashes","saveDashes","saveJumps","chaserCount",
        "sameTrackedPlayer","sameSpriteOwner","sameHairOwner")
INPUT_FIELDS=("moveX","moveY","aim","jumpCheck","jumpPressed","jumpReleased","jumpBuffer","dashCheck","dashPressed","dashBuffer","climb")
KINDS={"Entity":"scene_helper","WindController":"wind","Spikes":"spike","JumpthruPlatform":"jump_thru","Spring":"spring","Strawberry":"strawberry"}
OPAQUE_ENTITIES={"BackgroundTiles","ParticleSystem","TotalStrawberriesDisplay","SolidTiles"}
KEYS=("Left","Right","Up","Down","C","X","Z")
COMPONENTS={
    "BackgroundTiles":{"TileGrid"},"ParticleSystem":{"MirrorReflection"},"Entity":set(),"WindController":set(),
    "Spikes":{"LedgeBlocker","PlayerCollider","StaticMover","Image"},"TotalStrawberriesDisplay":{"StrawberriesCounter"},
    "SolidTiles":{"TileGrid","AnimatedTiles"},
    "Player":{"PlayerHair","PlayerSprite","Sprite","StateMachine","Leader","VertexLight","WaterInteraction","WindMover","SoundSource","MirrorReflection","Tween"},
    "JumpthruPlatform":{"Image"},"Strawberry":{"PlayerCollider","MirrorReflection","Follower","Sprite","Wiggler","BloomPoint","VertexLight","Tween"},
    "Spring":{"PlayerCollider","HoldableCollider","PufferCollider","Sprite","StaticMover","Wiggler"},
}

class Identities:
    def __init__(self):
        self.roles={}
        self.tokens={}
    def bind(self,role,token):
        if role in self.roles:
            require(self.roles[role]==token,"Recreated semantic object: "+role)
        else:
            require(token not in self.tokens,"Aliased semantic object: "+role)
            self.roles[role]=token
            self.tokens[token]=role
        return role
    def resolve(self,token):
        require(token in self.tokens,"Unobserved object owner/reference: "+str(token))
        return self.tokens[token]

def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]

def role_for_object(kind,room,authored_id):
    return f"room:{room}/{kind}:{authored_id}"

def constructor_geometry(object_definition):
    kind,_,_,_,size=object_definition
    if kind=="spike_up":return [size,3,0,-3]
    if kind=="spike_left":return [3,size,-3,0]
    if kind=="jump_thru":return [size,5,0,0]
    if kind=="spring":return [16,6,-8,-6]
    if kind=="strawberry":return [14,14,-7,-7]
    raise ValueError("Unsupported constructor geometry")

def source_projection(rows,rooms):
    summary=validate(rows)
    definitions=room_records(rooms)
    identities=Identities()
    phases=[row for row in rows if row.get("event")=="phase"]
    initial=phases[0]["state"]
    scopes={}
    records=[]
    for row in phases:
        state=row["state"]
        require(set(state)==set(FIELDS)|{"level","player","sprite","hair","rng","transition","entities","endOfFrame","pending","colliderOrder","nativeAttempts"},"Unknown SOURCE state leaf requires a fidelity decision")
        require(type(state["nativeAttempts"]) is int and state["nativeAttempts"]==0,"SOURCE native import guard reached")
        for key in ("level","player","sprite","hair"):
            require(type(state[key]) is str,"Invalid SOURCE identity type")
            identities.bind(key,state[key])
        identities.bind("rng",state["rng"]["identity"])
        entities=[]
        solid=None
        for entity in state["entities"]:
            require(set(entity)=={"id","type","Tag","Active","Visible","Collidable","position","scene","components","strawberryWobble","springWiggler"},"Unknown SOURCE entity leaf requires a fidelity decision")
            require(entity["scene"]==state["level"],"SOURCE live entity is not owned by the observed Level")
            require(type(entity["Visible"]) is bool,"Invalid SOURCE graphics visibility type")
            kind=entity["type"]
            if kind!="Strawberry":require(entity["strawberryWobble"] is None,"Unexpected SOURCE Strawberry private field owner")
            if kind!="Spring":require(entity["springWiggler"] is None,"Unexpected SOURCE Spring private field owner")
            require(kind in COMPONENTS,"Unknown SOURCE component owner")
            for component in entity["components"]:
                require(set(component)=={"id","type","Active","Visible"} and component["type"] in COMPONENTS[kind],"Unknown SOURCE component leaf requires a fidelity decision")
                require(type(component["Active"]) is bool and type(component["Visible"]) is bool,"Invalid SOURCE component flag type")
            if kind=="SolidTiles":
                identities.bind("solid",entity["id"])
                solid=entity["position"]
            if kind in OPAQUE_ENTITIES:
                continue
            if kind=="Player":
                require(entity["id"]==state["player"],"SOURCE tracked Player changed")
                entities.append({"role":"player","position":entity["position"],"tag":entity["Tag"],"active":entity["Active"],"collidable":entity["Collidable"]})
                continue
            require(kind in KINDS,"Unsupported SOURCE entity: "+kind)
            normalized=KINDS[kind]
            if normalized=="scene_helper":
                role=role_for_object(normalized,definitions[0]["name"],-1)
            elif normalized=="wind":
                role=identities.tokens.get(entity["id"],role_for_object(normalized,state["room"],-2))
            else:
                matches=[(room,obj) for room in definitions for obj in room["objects"]
                         if ("spike" if obj[0].startswith("spike_") else obj[0])==normalized and obj[2:4]==entity["position"]]
                require(len(matches)==1,"Ambiguous/missing authored SOURCE object")
                room,obj=matches[0]
                role=role_for_object(normalized,room["name"],obj[1])
            identities.bind(role,entity["id"])
            entry={"role":role,"position":entity["position"],"tag":entity["Tag"],"active":entity["Active"],"collidable":entity["Collidable"],
                   "box":None if normalized in ("scene_helper","wind") else constructor_geometry(obj)}
            if normalized=="jump_thru":entry["safe"]=True
            if normalized in ("spike","jump_thru"):entry["images"]=sum(component["type"]=="Image" for component in entity["components"])
            if normalized=="strawberry":entry["wobble"]=entity["strawberryWobble"]
            if normalized=="spring":entry["wiggler"]=entity["springWiggler"]
            entities.append(entry)
        require(solid is not None,"SOURCE global SolidTiles missing")
        value={key:state[key] for key in FIELDS}
        require(len(state["endOfFrame"])<=1,"Unsupported multiple EOF callbacks")
        value.update(entities=entities,solidOrigin=solid,collisionBounds=[state["bounds"][0],state["bounds"][0]+state["bounds"][2]],
                     pendingEOF=bool(state["endOfFrame"]),pending=[identities.resolve(token) for token in state["pending"]],
                     colliderOrder=[identities.resolve(token) for token in state["colliderOrder"]],rng={"calls":state["rng"]["calls"],"state":state["rng"]["state"]})
        transition=state["transition"]
        if transition is None:value["transition"]=None
        else:
            require(set(transition)=={"identity","Active","Finished","waitTimer","iterator"},"Unknown SOURCE coroutine leaf requires a fidelity decision")
            identities.bind("transition",transition["identity"])
            iterator=transition["iterator"]
            require(set(iterator)=={"state","cameraAt","cameraFrom","cameraTo","playerTo","outgoing","transitionOut","transitionIn"},"Unknown SOURCE iterator leaf requires a fidelity decision")
            require(iterator["state"] in (0,2),"Unrepresented SOURCE coroutine compiler state")
            require(iterator["transitionOut"] in (None,[]) and iterator["transitionIn"] in (None,[]),"Unsupported transition listeners")
            value["transition"]={"loaded":iterator["state"]!=0,"active":transition["Active"],"finished":transition["Finished"],"wait":transition["waitTimer"],
                **{key:iterator[key] for key in ("cameraAt","cameraFrom","cameraTo","playerTo")},
                "outgoing":None if iterator["outgoing"] is None else [identities.resolve(token) for token in iterator["outgoing"]]}
        if state["room"] not in scopes:
            definition=next(room for room in definitions if room["name"]==state["room"])
            scopes[state["room"]]={"event":"room-scope","tick":-1 if not scopes else row["tick"],"room":state["room"],"seed":definition["load_seed"]}
        records.append({"event":"phase","tick":row["tick"],"phase":row["phase"],"state":value})
    require(len(scopes)==2,"Missing SOURCE room materialization")
    inputs=[]
    for row in rows:
        if row.get("event")!="input":continue
        require(not set(row["keys"])-set(KEYS),"Unsupported SOURCE raw input")
        inputs.append({"event":"input","tick":row["tick"],**{key:row[key] for key in INPUT_FIELDS},"buttons":{key:key in row["keys"] for key in KEYS}})
    bootstrap={}
    for row in rows:
        if row.get("event")=="rng" and row["tick"]==-1:bootstrap.setdefault(row["random"],[]).append(row)
    require(len(bootstrap)==2,"Unexpected SOURCE initialization RNG scopes")
    room_bootstrap=list(bootstrap.values())[1]
    rng=[]
    for row in rows:
        if row.get("event")!="rng":continue
        if row["tick"]==-1:
            if row not in room_bootstrap:continue
            room=definitions[0]["name"]
        elif row["random"]==initial["rng"]["identity"]:room=""
        else:
            room=next(value["state"]["room"] for value in phases if value["tick"]==row["tick"] and value["phase"]=="before-eof")
        rng.append({"event":"rng","tick":row["tick"],"phase":row["phase"],"operation":row["operation"],"room":room,"calls":row["Calls"]})
    for scope in scopes.values():
        scope["calls"]=max(row["calls"] for row in rng if row["room"]==scope["room"])
    return {"phases":records,"inputs":inputs,"rng":rng,"scopes":list(scopes.values())},summary

def native_projection(rows):
    identities=Identities()
    phases=[row for row in rows if row.get("event")=="phase"]
    require(phases,"No actual native session observations")
    records=[]
    for row in phases:
        state=row["state"]
        for key in ("level","player"):
            require(type(state[key]) is int,"Invalid native lifetime token")
            identities.bind(key,state[key])
        require(type(state["presentation"]) is int,"Invalid presentation lifetime")
        for key,storage in (("sprite","spriteStorage"),("hair","hairStorage")):
            require(type(state[storage]) is str and state[storage].startswith("0x"),"Invalid native component storage")
            identities.bind(key,(state["presentation"],state[storage]))
        for key in ("worldStorage","collisionStorage","solidStorage","gridStorage"):
            require(type(state[key]) is str and state[key].startswith("0x"),"Invalid retained native world storage")
            identities.bind(key,(key,state[key]))
        require(type(state["rng"]["id"]) is int,"Invalid native RNG lifetime token")
        identities.bind("rng",state["rng"]["id"])
        words=state["rng"]["words"]
        require(len(words)==58 and all(type(word) is int for word in words),"Native RNG words require exact integer observations")
        entities=[]
        for entity in state["entities"]:
            require(type(entity["id"]) is int,"Invalid room object lifetime token")
            if entity["kind"]=="player":
                require(entity["id"]==state["player"],"Native roster contains a different Player")
                role="player"
            else:
                require(type(entity["authoredId"]) is int,"Invalid authored identity type")
                role=identities.bind(role_for_object(entity["kind"],entity["room"],entity["authoredId"]),entity["id"])
            entry={"role":role,"position":entity["position"],"tag":entity["tag"],"active":entity["active"],"collidable":entity["collidable"]}
            if entity["kind"]!="player":entry["box"]=entity["box"]
            if entity["kind"]=="jump_thru":entry["safe"]=entity["safe"]
            if entity["kind"] in ("spike","jump_thru"):entry["images"]=entity["images"]
            if entity["kind"]=="strawberry":entry["wobble"]=entity["wobble"]
            if entity["kind"]=="spring":
                require(entity["attached"]==state["solidStorage"],"Spring lost its actual static attachment")
                entry["wiggler"]=entity["wiggler"]
            entities.append(entry)
        value={key:state[key] for key in FIELDS}
        value.update(entities=entities,solidOrigin=state["solidOrigin"],collisionBounds=state["collisionBounds"],pendingEOF=state["pendingEOF"],pending=[identities.resolve(token) for token in state["pending"]],
                     colliderOrder=[identities.resolve(token) for token in state["colliderOrder"]],
                     rng={"calls":state["rng"]["calls"],"state":hashlib.sha256(json.dumps(words,separators=(",",":")).encode()).hexdigest()})
        transition=state["transition"]
        if transition is None:value["transition"]=None
        else:
            require(type(transition["id"]) is int,"Invalid native coroutine lifetime token")
            identities.bind("transition",transition["id"])
            value["transition"]={key:transition[key] for key in ("loaded","active","finished","wait","cameraAt","cameraFrom","cameraTo","playerTo")}
            if not transition["loaded"]:require(not transition["outgoing"],"Native outgoing roster captured before the coroutine update")
            value["transition"]["outgoing"]=None if not transition["loaded"] else [identities.resolve(token) for token in transition["outgoing"]]
        same(bool(transition and transition["loaded"]),state["ownsOutgoingRoom"],"native-outgoing-room-ownership")
        records.append({"event":"phase","tick":row["tick"],"phase":row["phase"],"state":value})
    inputs=[{key:row[key] for key in ("event","tick",*INPUT_FIELDS,"buttons")} for row in rows if row.get("event")=="input"]
    scopes=[row for row in rows if row.get("event")=="room-scope"]
    rng=[row for row in rows if row.get("event")=="rng"]
    return {"phases":records,"inputs":inputs,"rng":rng,"scopes":scopes}

def validate_native_end(native,frames,loads):
    ended=[row for row in native if row.get("event")=="native-ended"]
    require(len(ended)==1,"Native transition did not finish")
    same({"frames":frames,"reloads":0,"loads":loads},{key:ended[0][key] for key in ("frames","reloads","loads")},"native-ended")
    guards={row["member"]:row["rejected"] for row in native if row.get("event")=="native-guard"}
    same({"Spring.OnCollide":True,"Strawberry.OnPlayer":True,"Room2 death/reload":True,"Room2 diagnostic reload":True,"Dash/freeze crossing":True},guards,"native-guards")

def compare(reference,native,rooms):
    expected,summary=source_projection(reference,rooms)
    actual=native_projection(native)
    same(expected,actual,"native-transition")
    validate_native_end(native,summary["frames"],len(expected["scopes"]))
    return summary|{"source_only":False,"physical_or_native_proof":False,"native_cpu_semantic_comparison":True,"phases_compared":len(actual["phases"]),"fidelity":"Explicit semantic projection, not complete C# field/container parity"}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path);parser.add_argument("native",type=Path);parser.add_argument("rooms",type=Path)
    args=parser.parse_args()
    print(json.dumps(compare(read_rows(args.source),read_rows(args.native),json.loads(args.rooms.read_text())),indent=2))
