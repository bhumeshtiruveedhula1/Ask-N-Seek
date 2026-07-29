"""verify_fix_a.py — confirm color key removed from detector output"""
import sys
sys.path.insert(0, '.')
from backend.vision.object_detector import detect_keyframe

frame = r'outputs\frames_real\1192116-hd_1920_1080_30fps\0034.jpg'
dets = detect_keyframe(frame)

print('FIX A VERIFICATION')
print(f'  Total detections: {len(dets)}')
keys = sorted(dets[0].keys())
print(f'  Keys (first detection): {keys}')

assert 'color' not in keys, f'FAIL: color still present in {keys}'
assert 'class' in keys, 'FAIL: class missing'
assert 'bbox' in keys, 'FAIL: bbox missing'
assert 'confidence' in keys, 'FAIL: confidence missing'
assert 'spatial_relations' in keys, 'FAIL: spatial_relations missing'

print(f'  color present: False (CORRECT)')
print(f'  PASS: output keys == {keys}')
