"""Unknown-product recovery layer for ProductLens.

Uses UPCitemdb's free Explorer endpoint after the existing databases fail.
It only accepts a result when the returned UPC/EAN/GTIN matches the scanned
barcode, so an unrelated product can never be substituted.
"""
import os
import requests

UPC_API = "https://api.upcitemdb.com/prod/trial/lookup"


def _digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


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


def _lookup(barcode):
    try:
        response = requests.get(
            UPC_API,
            params={"upc": _digits(barcode)},
            headers={
                "Accept": "application/json",
                "User-Agent": "ProductLens/1.2 (student project)",
            },
            timeout=12,
        )
        if response.status_code != 200:
            print("UPCitemdb status:", response.status_code)
            return None
        data = response.json() or {}
        for item in data.get("items") or []:
            returned = item.get("ean") or item.get("upc") or item.get("gtin") or ""
            if _matches(barcode, returned):
                return item
    except (requests.RequestException, ValueError, TypeError):
        return None
    return None


def _make_product(appmod, item, barcode):
    name = (item.get("title") or "").strip()
    brand = (item.get("brand") or "").strip()
    description = (item.get("description") or "").strip()
    images = item.get("images") or []
    returned = item.get("ean") or item.get("upc") or item.get("gtin") or _digits(barcode)

    # UPCitemdb is an identity/catalogue source. It generally does not carry
    # nutrition or ingredient declarations, so do not fabricate those fields.
    product = {
        "name": name or "Product identified by barcode",
        "brands": brand,
        "barcode": str(returned),
        "image": images[0] if images else "",
        "ingredients": "",
        "allergens": "",
        "allergen_tags": "",
        "energy": 0,
        "sugar": 0,
        "fat": 0,
        "protein": 0,
        "salt": 0,
        "source": "UPCitemdb barcode catalogue",
        "verified": True,
        "catalog_description": description,
        "fssai_license": "",
        "fssai_source": "",
        "identity_recovered": True,
    }
    return appmod.finalize_product(product)


def install(appmod):
    original_search = appmod.search_product

    def search_with_unknown_recovery(barcode):
        product = original_search(barcode)
        if product:
            return product

        item = _lookup(barcode)
        if not item:
            return None

        product = _make_product(appmod, item, barcode)

        # Now that we have a verified product identity, try Open Food Facts
        # by name/brand. This can recover ingredients/nutrition even when the
        # original barcode is absent from OFF.
        name = product.get("name", "").strip()
        brand = product.get("brands", "").strip()
        if name:
            try:
                query = " ".join(x for x in [brand, name] if x)
                response = requests.get(
                    "https://world.openfoodfacts.org/api/v2/search",
                    params={
                        "search_terms": query,
                        "page_size": 10,
                        "fields": "code,product_name,product_name_en,brands,image_front_url,ingredients_text,ingredients_text_en,ingredients_text_with_allergens,ingredients_text_with_allergens_en,allergens,allergens_from_ingredients,allergens_tags,nutriments,packaging_text,packaging_text_en,labels,stores,manufacturing_places,producer",
                    },
                    headers={"User-Agent": "ProductLens/1.2 (student project)"},
                    timeout=12,
                )
                if response.ok:
                    candidates = (response.json() or {}).get("products") or []
                    for raw in candidates:
                        # Name/brand lookup is allowed only to enrich the
                        # already verified catalogue identity. Never replace
                        # its barcode with an unrelated OFF barcode.
                        raw_name = (raw.get("product_name") or raw.get("product_name_en") or "").strip().lower()
                        raw_brand = (raw.get("brands") or "").strip().lower()
                        if raw_name and name.lower() in raw_name or raw_name in name.lower():
                            if brand and raw_brand and brand.lower() not in raw_brand and raw_brand not in brand.lower():
                                continue
                            nutrition = raw.get("nutriments") or {}
                            enriched = dict(product)
                            enriched["ingredients"] = appmod.extract_off_ingredients(raw)
                            enriched["allergens"] = " ".join(str(v) for v in [raw.get("allergens"), raw.get("allergens_from_ingredients")] if v)
                            enriched["allergen_tags"] = " ".join(str(x) for x in (raw.get("allergens_tags") or []))
                            enriched["energy"] = nutrition.get("energy-kcal_100g", 0)
                            enriched["sugar"] = nutrition.get("sugars_100g", 0)
                            enriched["fat"] = nutrition.get("fat_100g", 0)
                            enriched["protein"] = nutrition.get("proteins_100g", 0)
                            enriched["salt"] = nutrition.get("salt_100g", 0)
                            enriched["image"] = raw.get("image_front_url") or product.get("image", "")
                            enriched["enrichment_source"] = "Open Food Facts product-name match"
                            product = appmod.finalize_product(enriched)
                            break
            except (requests.RequestException, ValueError, TypeError, KeyError):
                pass

        # Finally let the existing evidence-only AI layer explain whatever
        # verified identity/data is available; it still cannot invent facts.
        try:
            from intelligence_bootstrap import _safe_ai_gap_fill
            product = _safe_ai_gap_fill(appmod, product)
        except Exception:
            pass

        return product

    appmod.search_product = search_with_unknown_recovery
    return appmod.app


import app as _appmod
install(_appmod)
app = _appmod.app
