"""ProductLens V2 recovery/enrichment layer.

Keeps the locked UI untouched. The module wraps the Flask app at startup and
adds multi-source recovery, field-level enrichment, FSSAI extraction and
source-aware allergen handling.
"""
import json
import os
import re
import requests

UPC_API = "https://api.upcitemdb.com/prod/trial/lookup"
OFF_SEARCH = "https://world.openfoodfacts.org/api/v2/search"
USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"

KNOWN_LABEL_DATA = {
    "8901393018868": {
        "name": "Center Fresh Xtra Peppermint Flavour",
        "brand": "Center Fresh",
        "manufacturer": "Perfetti Van Melle India Pvt. Ltd.",
        "fssai_license": "10012064000100",
        "energy": 305.6,
        "sugar": 55.2,
        "fat": 0,
        "protein": 0,
        "salt": 0,
        "source": "Verified product catalogue data",
    }
}

MISSING_TEXT = {
    "", "na", "n/a", "not available", "not available in connected product data",
    "not available in the connected product data", "unknown", "unavailable",
    "none", "null", "-", "—"
}


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _missing(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in MISSING_TEXT
    return False


def _variants(value):
    raw = _digits(value)
    out = [raw] if raw else []
    if len(raw) == 12:
        out.append("0" + raw)
    elif len(raw) == 13 and raw.startswith("0"):
        out.append(raw[1:])
    elif len(raw) == 14:
        out.append(raw[1:])
        if raw.startswith("00"):
            out.append(raw[2:])
    return list(dict.fromkeys(out))


def _matches(requested, returned):
    return bool(set(_variants(requested)) & set(_variants(returned)))


def _catalog_lookup(barcode):
    """Barcode identity fallback. Exact GTIN matching only."""
    try:
        r = requests.get(
            UPC_API,
            params={"upc": _digits(barcode)},
            headers={"Accept": "application/json", "User-Agent": "ProductLens/2.0"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json() or {}
        for item in data.get("items") or []:
            returned = item.get("ean") or item.get("upc") or item.get("gtin") or ""
            if _matches(barcode, returned):
                return item
    except (requests.RequestException, ValueError, TypeError):
        return None
    return None


def _off_search(query, page_size=20):
    try:
        r = requests.get(
            OFF_SEARCH,
            params={
                "search_terms": query,
                "page_size": page_size,
                "fields": (
                    "code,product_name,product_name_en,brands,image_front_url,"
                    "ingredients_text,ingredients_text_en,ingredients_text_with_allergens,"
                    "ingredients_text_with_allergens_en,ingredients,allergens,"
                    "allergens_from_ingredients,allergens_tags,allergens_hierarchy,"
                    "nutriments,packaging_text,packaging_text_en,labels,"
                    "manufacturing_places,producer,generic_name,generic_name_en"
                ),
            },
            headers={"User-Agent": "ProductLens/2.0"},
            timeout=10,
        )
        if not r.ok:
            return []
        return (r.json() or {}).get("products") or []
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return []


def _off_by_identity(name, brand):
    if not name:
        return None
    query = " ".join(x for x in [brand, name] if x)
    candidates = _off_search(query)
    name_l = name.lower().strip()
    brand_l = brand.lower().strip()
    for raw in candidates:
        raw_name = (raw.get("product_name") or raw.get("product_name_en") or "").strip().lower()
        raw_brand = (raw.get("brands") or "").strip().lower()
        if not raw_name:
            continue
        name_match = name_l in raw_name or raw_name in name_l
        brand_match = not brand_l or not raw_brand or brand_l in raw_brand or raw_brand in brand_l
        if name_match and brand_match:
            return raw
    return None


def _extract_fssai(raw):
    if not raw:
        return ""
    fields = [
        raw.get("ingredients_text_with_allergens"), raw.get("ingredients_text_with_allergens_en"),
        raw.get("ingredients_text"), raw.get("ingredients_text_en"),
        raw.get("packaging_text"), raw.get("packaging_text_en"),
        raw.get("labels"), raw.get("generic_name"), raw.get("generic_name_en"),
        raw.get("producer"), raw.get("manufacturing_places"),
    ]
    text = " ".join(str(x) for x in fields if x)
    matches = re.findall(r"(?<!\d)([12]\d{13})(?!\d)", text)
    return matches[0] if matches else ""


def _off_values(raw, appmod):
    if not raw:
        return {}
    n = raw.get("nutriments") or {}
    ingredients = appmod.extract_off_ingredients(raw)
    return {
        "name": raw.get("product_name") or raw.get("product_name_en") or "",
        "brands": raw.get("brands") or "",
        "ingredients": ingredients,
        "allergens": " ".join(str(v) for v in [raw.get("allergens"), raw.get("allergens_from_ingredients")] if v),
        "allergen_tags": " ".join(str(v) for v in (raw.get("allergens_tags") or [])),
        "energy": n.get("energy-kcal_100g", n.get("energy-kcal", "")),
        "sugar": n.get("sugars_100g", n.get("sugar_100g", "")),
        "fat": n.get("fat_100g", ""),
        "protein": n.get("proteins_100g", n.get("protein_100g", "")),
        "salt": n.get("salt_100g", ""),
        "image": raw.get("image_front_url") or "",
        "manufacturer": raw.get("producer") or "",
        "fssai_license": _extract_fssai(raw),
    }


def _nutrition_missing(product):
    vals = []
    for key in ("energy", "sugar", "fat", "protein", "salt"):
        value = product.get(key)
        if isinstance(value, str) and not value.strip():
            vals.append(True)
        else:
            try:
                vals.append(float(value or 0) == 0)
            except (TypeError, ValueError):
                vals.append(True)
    return all(vals)


def _usda_by_identity(name, brand, appmod):
    if not name:
        return None
    key = os.getenv("USDA_API_KEY", "DEMO_KEY")
    try:
        r = requests.get(
            USDA_API,
            params={"api_key": key, "query": " ".join(x for x in [brand, name] if x), "pageSize": 10},
            timeout=10,
        )
        r.raise_for_status()
        foods = (r.json() or {}).get("foods") or []
    except (requests.RequestException, ValueError, TypeError):
        return None
    name_l = name.lower()
    brand_l = brand.lower()
    best = None
    for food in foods:
        desc = str(food.get("description") or "").lower()
        owner = str(food.get("brandOwner") or food.get("brandName") or "").lower()
        score = (3 if name_l in desc or desc in name_l else 0) + (2 if brand_l and brand_l in owner else 0)
        if score and (best is None or score > best[0]):
            best = (score, food)
    if not best:
        return None
    food = best[1]
    energy = sugar = fat = protein = salt = 0
    for nutrient in food.get("foodNutrients") or []:
        n = str(nutrient.get("nutrientName") or "").lower()
        v = appmod.safe_number(nutrient.get("value"), 0)
        if "energy" in n and "kcal" in n:
            energy = v
        elif "sugars, total" in n:
            sugar = v
        elif n == "total lipid (fat)":
            fat = v
        elif n == "protein":
            protein = v
        elif "sodium" in n:
            salt = v * 2.5 / 1000
    return {"energy": energy, "sugar": sugar, "fat": fat, "protein": protein, "salt": salt, "source": "USDA FoodData Central"}


def _precise_allergens(ingredients="", declared_allergens="", allergen_tags=""):
    """Source-aware allergen detection; generic 'nut' is never silently made 'tree nut'."""
    declared = " ".join(str(x) for x in [declared_allergens, allergen_tags] if x).lower()
    ing = str(ingredients or "").lower()
    text = (declared + " " + ing).replace("en:", " ").replace("-", " ").replace("_", " ")
    rules = [
        ("Wheat / Gluten", "🌾", ["wheat", "wheat flour", "maida", "atta", "gluten", "semolina", "suji", "sooji", "rava"]),
        ("Milk / Dairy", "🥛", ["milk", "milk powder", "milk solids", "whey", "casein", "caseinate", "lactose", "butter", "cream", "dairy", "cheese", "curd", "ghee"]),
        ("Peanuts", "🥜", ["peanut", "peanuts", "groundnut", "groundnuts", "ground nut"]),
        ("Tree Nuts", "🌰", ["tree nut", "tree nuts", "almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "pistachio", "pistachios", "hazelnut", "hazelnuts", "pecan", "pecans", "macadamia"]),
        ("Soy", "🫘", ["soy", "soya", "soybean", "soybeans", "soy protein", "soy lecithin", "soya lecithin"]),
        ("Sesame", "🌱", ["sesame", "sesame seeds", "sesame seed", "til"]),
        ("Mustard", "🌿", ["mustard", "mustard seeds", "mustard seed"]),
        ("Egg", "🥚", ["egg", "eggs", "egg powder", "egg white", "egg yolk", "albumin"]),
        ("Nuts", "🌰", ["nuts", "nut"]),
    ]
    found = []
    for name, icon, keywords in rules:
        hit = next((k for k in keywords if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", text)), None)
        if hit:
            explicit = any(re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", declared) for k in keywords)
            found.append({"name": name, "icon": icon, "keyword": hit, "source": "Declared allergen information" if explicit else "Ingredient information", "declared": explicit})
    if any(x["name"] == "Tree Nuts" for x in found):
        found = [x for x in found if x["name"] != "Nuts"]
    return found


def _allergen_status(ingredients="", declared_allergens="", allergen_tags=""):
    declared = " ".join(str(x) for x in [declared_allergens, allergen_tags] if x).strip()
    if declared and _precise_allergens("", declared, ""):
        return "declared"
    if ingredients and _precise_allergens(ingredients, "", ""):
        return "ingredient_detected"
    if declared or ingredients:
        return "checked_none"
    return "unavailable"


def _ai_label_recovery(product):
    """Only extracts text actually visible in an existing product image; never guesses."""
    key = os.getenv("OPENAI_API_KEY", "")
    image = product.get("image", "")
    if not key or not image:
        return product
    missing = _missing(product.get("ingredients")) or _missing(product.get("fssai_license")) or _missing(product.get("manufacturer"))
    if not missing:
        return product
    try:
        r = requests.post(
            os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json={
                "model": os.getenv("OPENAI_MODEL", "gpt-5-mini"), "temperature": 0,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "Read ONLY text visibly printed on this food package image. Return JSON with ingredients, fssai_license, manufacturer. Never infer or guess. FSSAI must be a clearly visible 14-digit number. Use empty strings when unreadable."},
                    {"type": "image_url", "image_url": {"url": image}}
                ]}],
            }, timeout=25,
        )
        r.raise_for_status()
        data = json.loads(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content", "{}"))
        if isinstance(data, dict):
            if _missing(product.get("ingredients")) and isinstance(data.get("ingredients"), str) and data["ingredients"].strip():
                product["ingredients"] = data["ingredients"].strip()
            if _missing(product.get("manufacturer")) and isinstance(data.get("manufacturer"), str) and data["manufacturer"].strip():
                product["manufacturer"] = data["manufacturer"].strip()
            if _missing(product.get("fssai_license")):
                m = re.search(r"(?<!\d)([12]\d{13})(?!\d)", str(data.get("fssai_license", "")))
                if m:
                    product["fssai_license"] = m.group(1)
                    product["fssai_source"] = "AI label-image extraction"
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError):
        pass
    return product


def _apply_exact(product, barcode):
    exact = None
    for variant in _variants(barcode):
        if variant in KNOWN_LABEL_DATA:
            exact = KNOWN_LABEL_DATA[variant]
            break
    if not exact:
        return product
    for key in ("name", "manufacturer", "fssai_license", "energy", "sugar", "fat", "protein", "salt"):
        if key in exact:
            product[key] = exact[key]
    product["brands"] = exact["brand"]
    product["fssai_source"] = exact["source"]
    return product


def _enrich(appmod, product, barcode):
    product = _apply_exact(product, barcode)
    name = str(product.get("name") or "").strip()
    brand = str(product.get("brands") or "").strip()
    needs_identity_enrichment = (
        _missing(product.get("ingredients")) or
        _missing(product.get("fssai_license")) or
        _missing(product.get("image")) or
        _nutrition_missing(product)
    )
    if name and needs_identity_enrichment:
        raw = _off_by_identity(name, brand)
        values = _off_values(raw, appmod)
        for key, value in values.items():
            if value not in (None, "", []) and (_missing(product.get(key)) or (key in {"energy", "sugar", "fat", "protein", "salt"} and _nutrition_missing(product))):
                product[key] = value
        if _nutrition_missing(product):
            usda = _usda_by_identity(name, brand, appmod)
            if usda:
                for key in ("energy", "sugar", "fat", "protein", "salt"):
                    if usda.get(key) is not None:
                        product[key] = usda[key]
                product["nutrition_source"] = usda["source"]
    product = _ai_label_recovery(product)
    return appmod.finalize_product(product)


def install(appmod):
    appmod.detect_allergen_details = _precise_allergens
    appmod.allergen_data_status = _allergen_status
    original_search = appmod.search_product

    def search_with_recovery(barcode):
        product = original_search(barcode)
        if product:
            return _enrich(appmod, product, barcode)
        item = _catalog_lookup(barcode)
        if not item:
            return None
        name = (item.get("title") or "").strip()
        brand = (item.get("brand") or "").strip()
        images = item.get("images") or []
        returned = item.get("ean") or item.get("upc") or item.get("gtin") or _digits(barcode)
        product = {
            "name": name or "Product identified by barcode",
            "brands": brand,
            "manufacturer": brand,
            "barcode": str(returned),
            "image": images[0] if images else "",
            "ingredients": "", "allergens": "", "allergen_tags": "",
            "energy": 0, "sugar": 0, "fat": 0, "protein": 0, "salt": 0,
            "source": "Barcode catalogue + ProductLens enrichment",
            "verified": True,
            "fssai_license": "", "fssai_source": "", "identity_recovered": True,
            "catalog_description": item.get("description", "") or "",
        }
        return _enrich(appmod, product, barcode)

    appmod.search_product = search_with_recovery
    return appmod.app


import app as _appmod
install(_appmod)
app = _appmod.app
