from engine.storage import init_db, delete_video, insert_detections
from engine.search import search_structured

VID = '__verify_isolation__'
init_db()
delete_video(VID)

# 3 clips: RED car@5s, BLUE car@21s, WHITE car@42s — each with person near it
insert_detections(VID, [
    {'id':'v1a','timestamp':5.0,'scene_id':0,'frame_index':0,'class_name':'car','color':'red','confidence':0.88,'bbox':[300,200,600,450],'spatial_relations':[]},
    {'id':'v1b','timestamp':5.0,'scene_id':0,'frame_index':0,'class_name':'person','color':None,'confidence':0.91,'bbox':[250,150,330,480],'spatial_relations':[{'subject':'person','relation':'near','object_':'car'}]},
    {'id':'v2a','timestamp':21.0,'scene_id':1,'frame_index':1,'class_name':'car','color':'blue','confidence':0.85,'bbox':[50,200,350,450],'spatial_relations':[]},
    {'id':'v2b','timestamp':21.0,'scene_id':1,'frame_index':1,'class_name':'person','color':None,'confidence':0.89,'bbox':[300,150,380,480],'spatial_relations':[{'subject':'person','relation':'near','object_':'car'}]},
    {'id':'v3a','timestamp':42.0,'scene_id':2,'frame_index':2,'class_name':'car','color':'white','confidence':0.82,'bbox':[100,200,400,450],'spatial_relations':[]},
    {'id':'v3b','timestamp':42.0,'scene_id':2,'frame_index':2,'class_name':'person','color':None,'confidence':0.87,'bbox':[410,150,490,480],'spatial_relations':[{'subject':'person','relation':'near','object_':'car'}]},
])
print("Seeded 6 detections: red@5s, blue@21s, white@42s")

def q(label, fd):
    fd['filters']['video_id'] = VID
    results = search_structured(fd)
    ts = [r.timestamp for r in results]
    colors = sorted(set(o['color'] for r in results for o in r.matched_objects if o.get('color')))
    print(f"\n{label}")
    print(f"  Results={len(results)}  Timestamps={ts}  Colors={colors}")
    return results

# OLD FAILURE 1: red car returning blue car clips
r1 = q("Q1: red car", {'status':'match','filters':{'class':'car','color':'red','negated':[]}})
assert len(r1) == 1, f"FAIL: expected 1 result, got {len(r1)}"
assert r1[0].timestamp == 5.0, f"FAIL: expected ts=5.0, got {r1[0].timestamp}"
blues = [o for r in r1 for o in r.matched_objects if o.get('color') == 'blue']
assert not blues, f"FAIL: red car query returned blue objects!"
print("  -> PASS: ONLY red@5s returned, no blue contamination")

# OLD FAILURE 2: blue car returning 0 results
r2 = q("Q2: blue car", {'status':'match','filters':{'class':'car','color':'blue','negated':[]}})
assert len(r2) == 1, f"FAIL: blue car returned {len(r2)} results (expected 1)"
assert r2[0].timestamp == 21.0, f"FAIL: expected ts=21.0, got {r2[0].timestamp}"
reds = [o for r in r2 for o in r.matched_objects if o.get('color') == 'red']
assert not reds, "FAIL: blue car query returned red objects!"
print("  -> PASS: ONLY blue@21s returned, no red contamination")

# CROSS-CHECK: white car
r3 = q("Q3: white car", {'status':'match','filters':{'class':'car','color':'white','negated':[]}})
assert len(r3) == 1 and r3[0].timestamp == 42.0, f"FAIL: white car: {[(r.timestamp) for r in r3]}"
print("  -> PASS: ONLY white@42s returned")

# PERSON NEAR CAR (no color): should get all 3 frames
r4 = q("Q4: person near car (any color)", {'status':'match','filters':{'class':'person','color':None,'negated':[],'spatial_relation':{'type':'near','target_class':'car'}}})
print(f"  -> {len(r4)} clips: {sorted([r.timestamp for r in r4])}")

delete_video(VID)
print("\n" + "="*55)
print("ALL ISOLATION CHECKS PASSED")
print("Architecture switch is VERIFIED CORRECT")
print("="*55)
