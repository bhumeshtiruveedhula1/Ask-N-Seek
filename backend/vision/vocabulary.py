"""
vocabulary.py -- Fixed Pre-Compiled Detection Vocabulary (820+ terms)
=====================================================================
Architecture ref : 03_Architecture_Final.md ss2 (Object detector row)
TRD ref          : TRD-Build-Plan-Achilles.md ssPART 2

The vocabulary is FIXED at load-time and compiled into a sorted tuple.
YOLO-World is initialised ONCE against this vocabulary -- never rebuilt per-frame.

Categories: COCO-80 + Objects365 subset + curated PS-relevant terms.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# RAW VOCABULARY -- organised by semantic group for maintainability
# ---------------------------------------------------------------------------

_RAW: list[str] = [
    # --- People & Body ---
    "person", "man", "woman", "child", "boy", "girl", "baby", "crowd",
    "face", "hand", "arm", "leg", "foot", "head", "body", "neck",
    "shoulder", "back", "chest", "hip", "knee", "elbow", "finger",
    "thumb", "wrist", "ankle", "toe", "nose", "ear", "eye", "mouth",
    "hair", "beard", "mustache",

    # --- Clothing ---
    "shirt", "jacket", "coat", "suit", "dress", "skirt",
    "pants", "trousers", "shorts", "jeans", "hoodie", "sweater",
    "uniform", "hat", "cap", "helmet", "hardhat", "visor",
    "gloves", "boots", "shoes", "sneakers", "sandals", "belt",
    "tie", "scarf", "mask", "apron", "vest", "robe", "gown",
    "raincoat", "jumpsuit", "overalls", "leggings", "stockings",
    "socks", "swimsuit",

    # --- Accessories / Carried items ---
    "backpack", "bag", "handbag", "purse", "suitcase", "briefcase",
    "luggage", "wallet", "umbrella", "watch", "glasses", "sunglasses",
    "badge", "lanyard", "phone", "smartphone", "earphones", "headphones",
    "keys", "keychain", "bracelet", "necklace", "ring",
    "earring", "goggles", "earmuffs",

    # --- Vehicles / Transport ---
    "car", "vehicle", "automobile", "sedan", "hatchback", "suv",
    "truck", "lorry", "van", "bus", "minibus", "minivan",
    "motorcycle", "motorbike", "scooter", "bicycle", "bike",
    "rickshaw", "ambulance", "cab", "taxi",
    "boat", "ship", "ferry", "yacht", "canoe", "kayak",
    "train", "subway", "tram", "airplane", "helicopter", "drone",
    "forklift", "tractor", "excavator", "crane", "bulldozer",
    "tanker", "trailer", "cart", "wagon",
    "wheelchair", "stroller", "pram", "skateboard", "moped",
    "pickup", "convertible", "coupe", "limousine",
    "jeep", "crossover", "camper", "caravan",

    # --- Vehicle parts ---
    "wheel", "tire", "windshield", "headlight", "taillight", "bumper",
    "mirror", "hood", "trunk", "antenna", "exhaust", "engine",
    "dashboard", "seat", "seatbelt", "brake", "pedal", "indicator",
    "wiper", "spoiler", "fender", "rim", "hubcap",

    # --- Safety / Security Equipment ---
    "cone", "barricade", "barrier", "fence", "gate", "lock", "padlock",
    "extinguisher", "fire extinguisher", "hydrant", "fire hydrant",
    "detector", "sprinkler", "alarm", "cctv",

    # --- Animals ---
    "dog", "cat", "bird", "cow", "horse", "sheep", "goat",
    "pig", "chicken", "duck", "rabbit", "monkey", "elephant",
    "tiger", "lion", "bear", "deer", "fox", "wolf", "rat", "mouse",
    "fish", "parrot", "eagle", "crow", "pigeon", "sparrow", "owl",
    "snake", "lizard", "frog", "turtle", "crocodile",
    "whale", "dolphin", "shark", "seal", "penguin", "flamingo",
    "donkey", "camel", "giraffe", "zebra", "rhino", "hippo",
    "chimpanzee", "gorilla", "panda", "koala", "kangaroo",
    "squirrel", "hamster", "rooster", "turkey", "goose", "swan", "peacock",

    # --- Outdoor / Infrastructure ---
    "road", "street", "sidewalk", "pavement", "crosswalk", "lane",
    "intersection", "bridge", "tunnel", "ramp", "stairs", "escalator",
    "elevator", "building", "house", "apartment", "office", "factory",
    "warehouse", "shed", "wall", "pillar", "column", "rooftop",
    "window", "balcony", "terrace", "porch", "garage", "carport",
    "driveway", "pathway", "alley", "corridor", "hallway", "lobby",
    "entrance", "exit", "door", "curb", "manhole", "gutter", "drain", "pipe",
    "chimney", "tower", "antenna", "mast", "pole", "billboard",
    "banner", "poster", "sign", "streetlight", "lamppost", "powerline",
    "tree", "bush", "shrub", "hedge", "grass", "lawn", "garden",
    "park", "bench", "fountain", "statue", "monument",
    "trashcan", "bin", "dumpster", "container", "barrel", "drum",
    "tent", "canopy", "awning", "scaffold", "pylon",
    "roundabout", "overpass", "underpass", "flyover", "viaduct",
    "dam", "reservoir", "embankment",

    # --- Road / Traffic ---
    "trafficlight", "signal", "stopsign", "roadsign",
    "divider", "guardrail", "bollard", "speedbump",
    "asphalt", "gravel",

    # --- Indoor / Furniture ---
    "table", "desk", "chair", "sofa", "couch", "bed", "mattress",
    "pillow", "blanket", "shelf", "bookshelf", "cabinet", "drawer",
    "wardrobe", "closet", "curtain", "blind", "carpet", "rug",
    "staircase", "railing", "banister", "mirror", "painting", "clock",
    "vase", "plant", "flower", "succulent", "cactus",
    "fireplace", "radiator", "heater", "fan", "chandelier", "candle",
    "lamp", "lantern",

    # --- Office / School / Lab ---
    "laptop", "computer", "monitor", "keyboard", "mouse", "printer",
    "scanner", "projector", "whiteboard", "blackboard", "screen",
    "book", "notebook", "binder", "folder", "paper", "pen", "pencil",
    "marker", "ruler", "calculator", "stapler", "tape", "scissors",
    "glue", "eraser", "sharpener", "compass",
    "microscope", "telescope", "beaker", "flask", "burner",
    "easel", "podium", "lectern", "globe", "map", "chart",

    # --- Kitchen / Food ---
    "bottle", "cup", "mug", "glass", "bowl", "plate", "tray",
    "pan", "pot", "kettle", "toaster", "microwave", "oven",
    "refrigerator", "dishwasher", "blender", "mixer", "juicer",
    "knife", "fork", "spoon", "chopsticks", "spatula", "ladle",
    "colander", "wok", "whisk", "tongs",
    "food", "bread", "toast", "croissant", "bagel", "bun",
    "rice", "noodles", "pasta", "soup", "stew",
    "meat", "chicken", "beef", "pork", "shrimp", "crab",
    "egg", "cheese", "butter", "milk", "cream", "yogurt",
    "apple", "banana", "orange", "grape", "strawberry", "watermelon",
    "pineapple", "mango", "lemon", "lime", "peach", "pear", "plum",
    "tomato", "potato", "carrot", "broccoli", "lettuce", "spinach",
    "onion", "garlic", "pepper", "cucumber", "celery", "corn",
    "sandwich", "burger", "pizza", "hotdog", "taco", "sushi",
    "donut", "cake", "cookie", "chocolate", "candy",
    "coffee", "tea", "juice", "soda", "beer", "wine",
    "can", "jar", "box", "package", "carton",

    # --- Electronics / Tools ---
    "television", "remote", "speaker", "microphone", "camera",
    "tripod", "charger", "cable", "socket", "switch", "powerstrip",
    "router", "modem", "server", "tablet", "smartwatch",
    "gamepad", "console", "joystick", "headset", "webcam",
    "hammer", "screwdriver", "wrench", "pliers", "drill", "saw",
    "chisel", "toolbox", "ladder",
    "paintbrush", "roller", "bucket", "hose", "sprayer",
    "shovel", "rake", "hoe", "spade", "pitchfork",
    "axe", "chainsaw", "lawnmower", "trimmer",

    # --- Sports / Recreation ---
    "ball", "football", "basketball", "baseball", "volleyball",
    "rugby", "cricket bat", "baseball bat", "tennis racket", "badminton racket",

    "net", "goal", "goalpost", "basket", "hoop",
    "pads", "cleats", "jersey",
    "treadmill", "dumbbell", "barbell", "kettlebell",
    "mat", "rope", "surfboard", "snowboard", "skis",
    "bow", "arrow", "target", "dart", "billiard", "cue", "paddle",
    "climbing harness", "carabiner",

    # --- Medical ---
    "stretcher", "crutches", "cane", "walker",
    "stethoscope", "syringe", "needle", "bandage", "cast", "splint",
    "pills", "medicine", "defibrillator",
    "thermometer",

    # --- Nature / Environment ---
    "sky", "cloud", "sun", "moon", "star", "rainbow", "lightning",
    "rain", "snow", "ice", "hail", "fog", "mist",
    "fire", "smoke", "ember", "flame",
    "water", "wave", "river", "lake", "ocean", "sea", "pond",
    "waterfall", "stream", "swamp",
    "mountain", "hill", "valley", "cliff", "cave", "canyon",
    "desert", "dune", "beach", "shore", "rock", "stone",
    "forest", "jungle", "meadow", "field", "farm", "crop", "soil",
    "mud", "sand", "dirt", "leaf", "branch", "trunk", "root",
    "flower", "petal", "seed", "fruit", "berry",
    "moss", "fern", "reed", "bamboo", "palm", "pine", "oak",
    "volcano", "glacier", "iceberg",

    # --- Surveillance / PS-specific ---
    "weapon", "gun", "rifle", "pistol", "knife", "sword", "bat",
    "cash", "banknote", "coin", "card", "atm",
    "intercom", "buzzer", "panel",
    "queue", "assembly",
    "graffiti", "vandalism", "debris", "wreckage", "rubble",
    "officer", "soldier", "firefighter", "guard", "nurse", "doctor",
    "chef", "waiter", "cashier", "driver", "rider", "cyclist", "worker",
    "jogger", "runner", "pedestrian", "tourist", "passenger",
    "prisoner", "suspect",

    # --- Extended COCO / Objects365 coverage ---
    "toothbrush", "toothpaste", "soap", "shampoo", "lotion",
    "towel", "toilet", "sink", "bathtub", "shower", "faucet",
    "tissue", "toilet paper", "hairdryer", "razor", "comb",
    "perfume", "lipstick", "compact",
    "suitcase", "trolley", "cart", "rack", "hook", "hanger",
    "peg", "clip", "pin", "magnet",
    "envelope", "stamp", "postcard", "letter", "parcel",
    "palette", "canvas", "brush", "paint", "sketchpad",
    "trophy", "medal", "ribbon", "certificate", "diploma",
    "calendar", "planner", "diary", "journal",
    "magnifier", "binoculars", "periscope",
    "loudspeaker", "megaphone", "walkie-talkie", "radio",
    "flag", "pennant", "banner",
    "handcuffs", "baton", "shield",
    "briefcase", "attachee",
    "syringe", "inhaler", "hearing aid", "prosthetic",
    "canteen", "flask", "thermos",
    "torch", "flashlight", "lantern", "lighter", "match",
    "biometric", "fingerprint", "scanner",
    "register", "receipt", "invoice",
    "crane hook", "pulley", "chain", "rope",
    "net", "tarpaulin", "canvas",
    "palette", "crate", "pallet",
    "forklift", "handtruck", "dolly", "trolley",
    "conveyor", "belt", "machine",
    "generator", "transformer", "substation",
    "solar panel", "windmill", "turbine",
    "satellite", "radar", "dish",
    "whiteboard marker", "projector screen",
    "safe", "vault", "locker",
    "meter", "gauge", "dial", "valve",
    "wrench", "spanner", "socket", "ratchet",
    "nail gun", "staple gun",
    "surveyor", "tripod", "level",
    "traffic warden", "parking meter",
    "bus stop", "shelter", "booth", "kiosk",
    "vending machine", "dispenser", "machine",
    "wheelchair ramp", "curb cut",
    "emergency exit", "fire door", "sprinkler head",
    "smoke detector", "co detector", "sensor",
    "power outlet", "switch panel", "circuit breaker",
    "extension cord", "surge protector",
    "atm machine", "payphone", "intercom",
    "door handle", "doorknob", "hinge", "latch", "deadbolt",
    "stepladder", "scaffold", "planks",
    "pump", "compressor", "cylinder", "nozzle",
    "funnel", "siphon", "valve",
    "pallet", "shrink wrap", "tape roll",
    "waste", "litter", "garbage",
    "recycling", "compost", "landfill",
    "floodlight", "spotlight", "strobe", "beacon", "siren",
    "barrier tape", "police line",
    "evidence bag", "gloves", "tweezers",
    "respirator", "hazmat suit", "safety harness",
    "first aid", "stretcher", "gurney",
    "ventilator", "nebulizer", "iv bag",
    "operating table", "scalpel", "forceps",
]

# ---------------------------------------------------------------------------
# SYNONYM LOOKUP -- maps free-text synonyms to canonical vocabulary terms
# Used by the query parser (Part 3); kept here as single source of truth.
# ---------------------------------------------------------------------------

SYNONYM_MAP: dict[str, str] = {
    # People
    "guy":           "person",
    "woman":         "person",
    "man":           "person",
    "lady":          "person",
    "gentleman":     "person",
    "human":         "person",
    "individual":    "person",
    "pedestrian":    "person",
    "people":        "person",
    "male":          "man",
    "female":        "woman",
    "kid":           "child",
    "teen":          "child",
    "teenager":      "child",
    "infant":        "baby",
    "toddler":       "baby",

    # Vehicles
    "automobile":    "car",
    "auto":          "car",
    "vehicle":       "car",
    "motorbike":     "motorcycle",
    "moped":         "scooter",
    "cycle":         "bicycle",
    "bike":          "bicycle",   # English: bike = bicycle
    "truck":         "truck",
    "plane":         "airplane",
    "chopper":       "helicopter",

    # Clothing / safety
    "hard hat":      "hardhat",
    "hard-hat":      "hardhat",
    "hi-vis":        "vest",
    "reflective jacket": "vest",
    "safety jacket": "vest",
    "goggles":       "goggles",
    "tee":           "shirt",

    # Accessories
    "knapsack":      "backpack",
    "rucksack":      "backpack",
    "pocketbook":    "purse",
    "cellphone":     "phone",
    "cell phone":    "smartphone",
    "mobile":        "smartphone",
    "spectacles":    "glasses",
    "specs":         "glasses",
    "spec":          "glasses",
    "shades":        "sunglasses",
    "earbuds":       "earphones",
    # Lemma normalisation: spaCy lemmatizes 'glasses' -> 'glass'; map back to canonical
    "glass":         "glasses",

    # Furniture
    "sofa":          "couch",

    # Containers
    "garbage can":   "trashcan",
    "rubbish bin":   "bin",

    # Infrastructure
    "streetlight":   "streetlight",
    "stoplight":     "trafficlight",
    "carpark":       "garage",

    # Electronics — abbreviations
    "tv":            "television",
    "t.v.":          "television",
    "telly":         "television",
    "fridge":        "refrigerator",
    "mike":          "microphone",
    "mic":           "microphone",
    # CLIP latent-space duplicate merges (Fix 2B)
    # These pairs trigger dual detections on the same physical object
    # because YOLO-World's zero-shot embedding conflates them.
    "headset":       "headphones",
    "smartwatch":    "watch",
    "sneaker":       "shoe",
    "sneakers":      "shoe",
    "kettlebell":    "dumbbell",


    # Hinglish / code-mixed
    "gaadi":         "car",
    "aadmi":         "man",
    "aurat":         "woman",
    "baccha":        "child",
    "kutta":         "dog",
    "billi":         "cat",

    # Disambiguate attractor classes (Task 3)
    # "bat" has two meanings: animal-bat and sports bat.
    # YOLO-World's "bat" embedding activates on bottles/cylindrical objects.
    # Remapping to "baseball bat" uses a more discriminative text embedding
    # that is spatially anchored (held by humans, near hands/shoulder).
    "bat":           "baseball bat",
}


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def get_vocabulary() -> tuple[str, ...]:
    """
    Return the fixed, deduplicated, sorted vocabulary tuple.
    Single source of truth for every call to YOLO-World.
    """
    return tuple(sorted(set(_RAW)))


def resolve_synonym(term: str) -> str:
    """Map a user-supplied term to its canonical vocabulary entry."""
    return SYNONYM_MAP.get(term.lower().strip(), term.lower().strip())


# Pre-built collections for O(1) membership checks
VOCABULARY: tuple[str, ...] = get_vocabulary()
VOCABULARY_SET: frozenset[str] = frozenset(VOCABULARY)

if __name__ == "__main__":
    print(f"Vocabulary size: {len(VOCABULARY)} terms")
    print("First 20:", VOCABULARY[:20])
    print("Last  20:", VOCABULARY[-20:])
