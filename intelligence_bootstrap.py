"""ProductLens deployment intelligence layer.

Loaded by Render before the Flask app. Keeps the existing interface while
adding strict barcode validation, broader database fallback, FSSAI recovery,
AI-assisted evidence-only gap filling, and reliable result auto-scroll.
"""
import json
import os
import re
import requests

OFF_SEARCH = "https://world.openfoodfacts.org/api/v2/search"
USDA_API = "https://api.nal.usda.gov/fdc/v1/foods/search"
HEADERS = {"User-Agent": "ProductLens/1.1 (student project)"}


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _barcode_variants(barcode):
    raw = _digits(barcode)
    values = [raw] if raw else []
    if len(raw) == 12:
        values.append("0" + raw)
    if len(raw) == 13 and raw.startswith("0"):
        values.append(raw[1:])
    if len(raw) == 14:
        values.append(raw[1:])
        if raw.startswith("00"):
            values.append(raw[2:])
    return list(dict.fromkeys(values))


def _same_product_barcode(requested, returned):
    wanted = set(_barcode_variants(requested))
    got = set(_barcode_variants(returned))
    return bool(wanted and got and wanted.intersection(got))


def _extract_fssai(text):
    if not text:
        return ""
    matches = re.findall(r"(?<!\d)([12]\d{13})(?!\d)", str(text))
    return matches[0] if matches else ""


def _fssai_from_off(raw):
    fields = [
        raw.get("packaging_text"), raw.get("packaging_text_en"),
        raw.get("ingredients_text_with_allergens"),
        raw.get("ingredients_text_with_allergens_en"),
        raw.get("ingredients_text"), raw.get("ingredients_text_en"),
        raw.get("generic_name"), raw.get("generic_name_en"),
        raw.get("manufacturing_places"), raw.get("labels"),
        raw.get("stores"), raw.get("origins"), raw.get("producer"),
    ]
    return _extract_fssai(" ".join(str(x) for x in fields if x))


def _fetch_off_exact(barcode):
    """Return OFF data only when the returned GTIN matches the scanned code."""
    for code in _barcode_variants(barcode):
        try:
            response = requests.get(
                OFF_SEARCH,
                params={
                    "code": code,
                    "page_size": 10,
                    "fields": (
                        "code,product_name,product_name_en,brands,image_front_url,"
                        "ingredients_text,ingredients_text_en,ingredients_text_with_allergens,"
                        "ingredients_text_with_allergens_en,allergens,allergens_from_ingredients,"
                        "allergens_tags,allergens_hierarchy,nutriments,packaging_text,"
                        "packaging_text_en,generic_name,generic_name_en,manufacturing_places,"
                        "labels,stores,origins,producer"
                    ),
                },
                headers=HEADERS,
                timeout=12,
            )
            response.raise_for_status()
            products = (response.json() or {}).get("products") or []
            for raw in products:
                if _same_product_barcode(barcode, raw.get("code", "")):
                    return raw
        except (requests.RequestException, ValueError, TypeError):
            continue
    return None


def _product_from_off(appmod, raw, requested):
    nutrition = raw.get("nutriments") or {}
    ingredients = appmod.extract_off_ingredients(raw)
    allergens = " ".join(
        str(v) for v in [
            raw.get("allergens"), raw.get("allergens_from_ingredients"),
            raw.get("allergens_hierarchy")
        ] if v
    )
    fssai = _fssai_from_off(raw)
    product = {
        "name": raw.get("product_name") or raw.get("product_name_en") or "Unknown Product",
        "brands": raw.get("brands", ""),
        "barcode": raw.get("code") or str(requested),
        "image": raw.get("image_front_url", ""),
        "ingredients": ingredients,
        "allergens": allergens,
        "allergen_tags": " ".join(str(x) for x in (raw.get("allergens_tags") or [])),
        "energy": nutrition.get("energy-kcal_100g", nutrition.get("energy-kcal", 0)),
        "sugar": nutrition.get("sugars_100g", nutrition.get("sugar_100g", 0)),
        "fat": nutrition.get("fat_100g", 0),
        "protein": nutrition.get("proteins_100g", nutrition.get("protein_100g", 0)),
        "salt": nutrition.get("salt_100g", 0),
        "source": "Open Food Facts",
        "verified": True,
        "fssai_license": fssai,
        "fssai_source": "Open Food Facts label data" if fssai else "",
    }
    return appmod.finalize_product(product)


def _usda_exact(appmod, barcode):
    key = os.getenv("USDA_API_KEY", "DEMO_KEY")
    try:
        response = requests.get(
            USDA_API,
            params={"api_key": key, "query": str(barcode), "pageSize": 25},
            timeout=12,
        )
        response.raise_for_status()
        foods = (response.json() or {}).get("foods") or []
    except (requests.RequestException, ValueError, TypeError):
        return None

    for food in foods:
        gtin = food.get("gtinUpc") or food.get("gtin_upc") or food.get("upc") or ""
        if not _same_product_barcode(barcode, gtin):
            continue
        nutrients = food.get("foodNutrients") or []
        energy = sugar = fat = protein = sodium = 0
        for n in nutrients:
            name = str(n.get("nutrientName", "")).lower()
            value = appmod.safe_number(n.get("value", 0))
            if "energy" in name:
                energy = value
            elif "sugars, total" in name:
                sugar = value
            elif name == "total lipid (fat)":
                fat = value
            elif name == "protein":
                protein = value
            elif "sodium" in name:
                sodium = value
        product = {
            "name": food.get("description") or "Unknown Product",
            "brands": food.get("brandOwner", ""),
            "barcode": str(gtin), "image": "",
            "ingredients": food.get("ingredients") or "",
            "allergens": "", "allergen_tags": "",
            "energy": energy, "sugar": sugar, "fat": fat,
            "protein": protein, "salt": sodium * 2.5 / 1000,
            "source": "USDA FoodData Central", "verified": True,
            "fssai_license": "", "fssai_source": "",
        }
        return appmod.finalize_product(product)
    return None


def _safe_ai_gap_fill(appmod, product):
    """Use AI only to interpret evidence already present; never invent facts."""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return product
    missing = [k for k in ("ingredients", "allergens", "fssai_license") if not product.get(k)]
    if not missing:
        return product

    evidence = {
        "barcode": product.get("barcode", ""),
        "name": product.get("name", ""),
        "brand": product.get("brands", ""),
        "ingredients": product.get("ingredients", ""),
        "source": product.get("source", ""),
        "missing_fields": missing,
    }
    prompt = (
        "You are a food-product data recovery layer. Use only the supplied evidence. "
        "Never invent a product, barcode, ingredient, allergen, adulteration claim, or FSSAI number. "
        "For FSSAI, return a number only if the supplied evidence explicitly contains a 14-digit number. "
        "Return JSON with keys ingredients, allergens, fssai_license, summary_points. "
        "Use empty strings/lists when evidence is insufficient.\n" + json.dumps(evidence, ensure_ascii=False)
    )
    try:
        url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
        model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
        r = requests.post(
            url,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json={
                "model": model, "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=20,
        )
        r.raise_for_status()
        content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content", "")
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            if not product.get("ingredients") and isinstance(parsed.get("ingredients"), str):
                product["ingredients"] = parsed["ingredients"].strip()
            if not product.get("allergens"):
                a = parsed.get("allergens")
                if isinstance(a, list):
                    product["allergens"] = ", ".join(str(x).strip() for x in a if str(x).strip())
                elif isinstance(a, str):
                    product["allergens"] = a.strip()
            if not product.get("fssai_license"):
                candidate = _extract_fssai(parsed.get("fssai_license", ""))
                if candidate:
                    product["fssai_license"] = candidate
                    product["fssai_source"] = "AI-recovered from supplied evidence"
            if isinstance(parsed.get("summary_points"), list):
                product["ai_summary_points"] = [str(x).strip() for x in parsed["summary_points"] if str(x).strip()]
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError):
        pass

    product = appmod.finalize_product(product)
    if product.get("ai_summary_points"):
        existing = product.get("product_summary") or []
        existing.extend({"icon": "🧠", "title": "AI Evidence Insight", "text": x} for x in product["ai_summary_points"])
        product["product_summary"] = existing[:6]
    return product


def install(appmod):
    original_search = appmod.search_product
    original_finalize = appmod.finalize_product

    def finalize_with_metadata(product):
        product.setdefault("fssai_license", "")
        product.setdefault("fssai_source", "")
        return original_finalize(product)

    appmod.finalize_product = finalize_with_metadata

    def strict_search(barcode):
        requested = _digits(barcode)
        product = original_search(requested)
        if product and _same_product_barcode(requested, product.get("barcode", "")):
            if not product.get("fssai_license"):
                exact = _fetch_off_exact(requested)
                if exact:
                    product["fssai_license"] = _fssai_from_off(exact)
                    if product["fssai_license"]:
                        product["fssai_source"] = "Open Food Facts label data"
            return _safe_ai_gap_fill(appmod, product)

        raw = _fetch_off_exact(requested)
        if raw:
            return _safe_ai_gap_fill(appmod, _product_from_off(appmod, raw, requested))

        product = _usda_exact(appmod, requested)
        if product:
            return _safe_ai_gap_fill(appmod, product)

        return None

    appmod.search_product = strict_search

    @appmod.app.route("/health")
    def health():
        return "ok", 200

    # Preserve the existing page design but make analysis results reliably
    # visible after a POST, including on mobile browsers.
    @appmod.app.after_request
    def productlens_scroll_fix(response):
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type and response.status_code == 200:
            try:
                body = response.get_data(as_text=True)
                marker = "</body>"
                script = """
<script>
(function () {
  function showAnalysis() {
    var results = document.getElementById('analysisResults');
    if (!results) return;
    setTimeout(function () {
      var top = results.getBoundingClientRect().top + window.pageYOffset - 18;
      window.scrollTo({ top: Math.max(0, top), left: 0, behavior: 'smooth' });
    }, 180);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', showAnalysis, {once:true});
  } else {
    showAnalysis();
  }
})();
</script>
"""
                if marker in body and "productlens_scroll_fix" not in body:
                    body = body.replace(marker, script + "\n" + marker, 1)
                    response.set_data(body)
            except Exception:
                pass
        return response

    return appmod.app


from app import app as _flask_app
install(__import__("app"))
app = _flask_app
