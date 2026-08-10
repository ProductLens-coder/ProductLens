"""ProductLens backend recovery layer.

IMPORTANT: this module changes backend behaviour only. The existing UI is untouched.
It wraps app.py because Render starts `unknown_fallback:app`.
"""
import os
import re
import requests

OFF_PRODUCT = "https://world.openfoodfacts.org/api/v2/product/{}.json"
OFF_SEARCH = "https://world.openfoodfacts.org/api/v2/search"
USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"
UPC_API = "https://api.upcitemdb.com/prod/trial/lookup"
HEADERS = {"User-Agent": "ProductLens/2.0 (student food intelligence project)"}
MISSING = {"", "na", "n/a", "not available", "unavailable", "unknown", "none", "null", "-", "—"}

# Existing verified record retained; this is not used to manufacture data for other barcodes.
KNOWN = {
    "8901393018868": {
        "name": "Center Fresh Xtra Peppermint Flavour",
        "brand": "Center Fresh",
        "manufacturer": "Perfetti Van Melle India Pvt. Ltd.",
        "fssai_license": "10012064000100",
        "energy": 305.6, "sugar": 55.2, "fat": 0, "protein": 0, "salt": 0,
        "source": "Verified product catalogue data",
    }
}


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


def missing(value):
    return value is None or (isinstance(value, str) and value.strip().lower() in MISSING)


def variants(value):
    raw = digits(value)
    if not raw:
        return []
    out = [raw]
    if len(raw) == 12:
        out.append("0" + raw)
    elif len(raw) == 13 and raw.startswith("0"):
        out.append(raw[1:])
    elif len(raw) == 14:
        out.append(raw[1:])
        if raw.startswith("00"):
            out.append(raw[2:])
    return list(dict.fromkeys(out))


def same_barcode(a, b):
    return bool(set(variants(a)) & set(variants(b)))


def exact_off(barcode):
    """Direct exact barcode lookup. This must run before any identity guessing."""
    for code in variants(barcode):
        try:
            r = requests.get(
                OFF_PRODUCT.format(code),
                params={
                    "fields": "code,product_name,product_name_en,brands,image_front_url,ingredients_text,ingredients_text_en,ingredients_text_with_allergens,ingredients_text_with_allergens_en,allergens,allergens_from_ingredients,allergens_tags,allergens_hierarchy,nutriments,producer,manufacturing_places,packaging_text,packaging_text_en,generic_name,generic_name_en,labels"
                },
                headers=HEADERS,
                timeout=12,
            )
            if not r.ok:
                continue
            raw = r.json() or {}
            if raw.get("status") == 1 and isinstance(raw.get("product"), dict):
                p = raw["product"]
                if same_barcode(barcode, p.get("code", code)):
                    return p
        except (requests.RequestException, ValueError, TypeError):
            continue
    return None


def off_search_barcode(barcode):
    """Exact-code search fallback for installations where the product endpoint differs."""
    for code in variants(barcode):
        try:
            r = requests.get(
                OFF_SEARCH,
                params={
                    "code": code, "page_size": 10,
                    "fields": "code,product_name,product_name_en,brands,image_front_url,ingredients_text,ingredients_text_en,ingredients_text_with_allergens,ingredients_text_with_allergens_en,allergens,allergens_from_ingredients,allergens_tags,allergens_hierarchy,nutriments,producer,manufacturing_places,packaging_text,packaging_text_en,generic_name,generic_name_en,labels"
                },
                headers=HEADERS,
                timeout=12,
            )
            if not r.ok:
                continue
            for p in (r.json() or {}).get("products", []) or []:
                if same_barcode(barcode, p.get("code", "")):
                    return p
        except (requests.RequestException, ValueError, TypeError):
            continue
    return None


def upc_identity(barcode):
    """Last barcode-identity fallback. It is accepted only for an exact GTIN match."""
    try:
        r = requests.get(
            UPC_API,
            params={"upc": digits(barcode)},
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code != 200:
            return None
        for item in (r.json() or {}).get("items", []) or []:
            returned = item.get("ean") or item.get("upc") or item.get("gtin") or ""
            if same_barcode(barcode, returned):
                return item
    except (requests.RequestException, ValueError, TypeError):
        return None
    return None


def off_identity_search(name, brand):
    """Use OFF search only after a product identity has been established elsewhere."""
    if not name:
        return None
    query = " ".join(x for x in (brand, name) if x)
    try:
        r = requests.get(
            OFF_SEARCH,
            params={
                "search_terms": query, "page_size": 25,
                "fields": "code,product_name,product_name_en,brands,image_front_url,ingredients_text,ingredients_text_en,ingredients_text_with_allergens,ingredients_text_with_allergens_en,allergens,allergens_from_ingredients,allergens_tags,allergens_hierarchy,nutriments,producer,manufacturing_places,packaging_text,packaging_text_en,generic_name,generic_name_en,labels"
            },
            headers=HEADERS,
            timeout=12,
        )
        if not r.ok:
            return None
        nl, bl = name.lower().strip(), brand.lower().strip()
        best, score_best = None, -1
        for p in (r.json() or {}).get("products", []) or []:
            pn = str(p.get("product_name") or p.get("product_name_en") or "").lower().strip()
            pb = str(p.get("brands") or "").lower().strip()
            if not pn:
                continue
            score = 0
            if pn == nl: score += 5
            elif nl in pn or pn in nl: score += 3
            if bl and pb and (bl in pb or pb in bl): score += 3
            if score > score_best:
                best, score_best = p, score
        return best if score_best >= 3 else None
    except (requests.RequestException, ValueError, TypeError):
        return None


def fssai_from_text(*values):
    text = " ".join(str(v) for v in values if v)
    m = re.search(r"(?<!\d)([12]\d{13})(?!\d)", text)
    return m.group(1) if m else ""


def extract_allergen_details(ingredients="", declared="", tags=""):
    """Evidence-first allergen handling. Generic nuts are never silently converted to tree nuts."""
    declared_text = " ".join(str(x) for x in (declared, tags) if x).lower()
    ingredient_text = str(ingredients or "").lower()
    combined = (declared_text + " " + ingredient_text).replace("en:", " ").replace("-", " ").replace("_", " ")
    rules = [
        ("Wheat / Gluten", "🌾", ["wheat", "wheat flour", "maida", "atta", "gluten", "semolina", "suji", "sooji", "rava"]),
        ("Milk / Dairy", "🥛", ["milk", "milk powder", "milk solids", "whey", "casein", "caseinate", "lactose", "butter", "cream", "dairy", "cheese", "curd", "ghee"]),
        ("Peanuts", "🥜", ["peanut", "peanuts", "groundnut", "groundnuts", "ground nut"]),
        ("Tree Nuts", "🌰", ["tree nut", "tree nuts", "almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "pistachio", "pistachios", "hazelnut", "hazelnuts", "pecan", "pecans", "macadamia"]),
        ("Soy", "🫘", ["soy", "soya", "soybean", "soybeans", "soy protein", "soy lecithin", "soya lecithin"]),
        ("Sesame", "🌱", ["sesame", "sesame seed", "sesame seeds", "til"]),
        ("Mustard", "🌿", ["mustard", "mustard seed", "mustard seeds"]),
        ("Egg", "🥚", ["egg", "eggs", "egg powder", "egg white", "egg yolk", "albumin"]),
        ("Nuts", "🌰", ["nuts", "nut"]),
    ]
    found = []
    for name, icon, keys in rules:
        hit = next((k for k in keys if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", combined)), None)
        if hit:
            is_declared = any(re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", declared_text) for k in keys)
            found.append({"name": name, "icon": icon, "keyword": hit, "source": "Declared allergen information" if is_declared else "Ingredient information", "declared": is_declared})
    if any(x["name"] == "Tree Nuts" for x in found):
        found = [x for x in found if x["name"] != "Nuts"]
    return found


def nutrition_missing(p):
    return all(missing(p.get(k)) or p.get(k) == 0 for k in ("energy", "sugar", "fat", "protein", "salt"))


def off_values(raw, app):
    if not raw:
        return {}
    n = raw.get("nutriments") or {}
    return {
        "name": raw.get("product_name") or raw.get("product_name_en") or "",
        "brands": raw.get("brands") or "",
        "ingredients": app.extract_off_ingredients(raw),
        "allergens": " ".join(str(x) for x in (raw.get("allergens"), raw.get("allergens_from_ingredients"), raw.get("allergens_hierarchy")) if x),
        "allergen_tags": " ".join(str(x) for x in (raw.get("allergens_tags") or [])),
        "image": raw.get("image_front_url") or "",
        "manufacturer": raw.get("producer") or "",
        "energy": n.get("energy-kcal_100g", n.get("energy-kcal", "")),
        "sugar": n.get("sugars_100g", n.get("sugar_100g", "")),
        "fat": n.get("fat_100g", ""),
        "protein": n.get("proteins_100g", n.get("protein_100g", "")),
        "salt": n.get("salt_100g", ""),
        "fssai_license": fssai_from_text(raw.get("packaging_text"), raw.get("packaging_text_en"), raw.get("ingredients_text_with_allergens"), raw.get("ingredients_text_with_allergens_en"), raw.get("labels"), raw.get("producer")),
    }


def merge_missing(product, values):
    for k, v in values.items():
        if v not in (None, "", []) and missing(product.get(k)):
            product[k] = v


def enrich(app, product, barcode):
    # Exact known record first; no data is invented for other barcodes.
    for code in variants(barcode):
        if code in KNOWN:
            d = KNOWN[code]
            product["name"] = d["name"]
            product["brands"] = d["brand"]
            product["manufacturer"] = d["manufacturer"]
            product["fssai_license"] = d["fssai_license"]
            for k in ("energy", "sugar", "fat", "protein", "salt"):
                product[k] = d[k]
            product["source"] = d["source"]
            break

    name = str(product.get("name") or "").strip()
    brand = str(product.get("brands") or "").strip()

    # Once identity is known, enrich individual missing fields from OFF.
    if name:
        merge_missing(product, off_values(off_identity_search(name, brand), app))

    # Nutrition fallback is identity-based, not a blind barcode search.
    if name and nutrition_missing(product):
        try:
            r = requests.get(USDA_API, params={"api_key": os.getenv("USDA_API_KEY", "DEMO_KEY"), "query": f"{brand} {name}", "pageSize": 10}, timeout=12)
            foods = (r.json() or {}).get("foods") or [] if r.ok else []
            best = None
            nl, bl = name.lower(), brand.lower()
            for food in foods:
                desc = str(food.get("description") or "").lower()
                owner = str(food.get("brandOwner") or food.get("brandName") or "").lower()
                score = (3 if nl in desc or desc in nl else 0) + (2 if bl and bl in owner else 0)
                if score and (best is None or score > best[0]): best = (score, food)
            if best:
                vals = {"energy": 0, "sugar": 0, "fat": 0, "protein": 0, "salt": 0}
                for n in best[1].get("foodNutrients") or []:
                    nn = str(n.get("nutrientName") or "").lower(); v = app.safe_number(n.get("value"), 0)
                    if "energy" in nn and "kcal" in nn: vals["energy"] = v
                    elif "sugars, total" in nn: vals["sugar"] = v
                    elif nn == "total lipid (fat)": vals["fat"] = v
                    elif nn == "protein": vals["protein"] = v
                    elif "sodium" in nn: vals["salt"] = v * 2.5 / 1000
                for k, v in vals.items():
                    if product.get(k) in (None, "", 0): product[k] = v
                product["nutrition_source"] = "USDA FoodData Central"
        except (requests.RequestException, ValueError, TypeError):
            pass

    return app.finalize_product(product)


def recover(app, barcode):
    requested = digits(barcode)
    if not requested:
        return None

    # 1. Exact Open Food Facts endpoint — the most important missing fallback.
    raw = exact_off(requested) or off_search_barcode(requested)
    if raw:
        p = {
            "name": raw.get("product_name") or raw.get("product_name_en") or "",
            "brands": raw.get("brands") or "",
            "manufacturer": raw.get("producer") or "",
            "barcode": raw.get("code") or requested,
            "image": raw.get("image_front_url") or "",
            "ingredients": app.extract_off_ingredients(raw),
            "allergens": " ".join(str(x) for x in (raw.get("allergens"), raw.get("allergens_from_ingredients"), raw.get("allergens_hierarchy")) if x),
            "allergen_tags": " ".join(str(x) for x in (raw.get("allergens_tags") or [])),
            "energy": (raw.get("nutriments") or {}).get("energy-kcal_100g", 0),
            "sugar": (raw.get("nutriments") or {}).get("sugars_100g", 0),
            "fat": (raw.get("nutriments") or {}).get("fat_100g", 0),
            "protein": (raw.get("nutriments") or {}).get("proteins_100g", 0),
            "salt": (raw.get("nutriments") or {}).get("salt_100g", 0),
            "fssai_license": fssai_from_text(raw.get("packaging_text"), raw.get("packaging_text_en"), raw.get("ingredients_text_with_allergens"), raw.get("ingredients_text_with_allergens_en"), raw.get("labels"), raw.get("producer")),
            "source": "Open Food Facts",
            "verified": True,
        }
        return enrich(app, p, requested)

    # 2. Barcode identity catalogue fallback.
    item = upc_identity(requested)
    if item:
        images = item.get("images") or []
        p = {
            "name": item.get("title") or "",
            "brands": item.get("brand") or "",
            "manufacturer": item.get("manufacturer") or item.get("brand") or "",
            "barcode": str(item.get("ean") or item.get("upc") or item.get("gtin") or requested),
            "image": images[0] if images else "",
            "ingredients": "", "allergens": "", "allergen_tags": "",
            "energy": 0, "sugar": 0, "fat": 0, "protein": 0, "salt": 0,
            "fssai_license": "", "source": "Barcode identity catalogue", "verified": True,
        }
        return enrich(app, p, requested)

    return None


def install(module):
    # Replace allergen logic with the stricter version while preserving the UI.
    module.detect_allergen_details = extract_allergen_details

    original = module.search_product

    def wrapped(barcode):
        requested = digits(barcode)
        product = original(requested)
        if product:
            # Never accept a record whose barcode does not match the scanned code.
            if same_barcode(requested, product.get("barcode", requested)):
                return enrich(module, product, requested)
        return recover(module, requested)

    module.search_product = wrapped
    return module.app


from app import app as _app
install(__import__("app"))
app = _app
