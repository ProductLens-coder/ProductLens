from pathlib import Path
import re

path = Path("app.py")
text = path.read_text(encoding="utf-8")
start = text.index("def decode_ingredients(ingredients):")
end = text.index("\n# =========================================================\n# PRODUCT SUMMARY", start)

new_function = '''def decode_ingredients(ingredients):
    """Explain every listed ingredient without silently dropping unknown items."""
    if not ingredients:
        return []

    raw_items = get_ingredient_order(ingredients)
    if not raw_items:
        return []

    guide = {
        "potato": ("Base vegetable ingredient", "Provides the main potato component and contributes carbohydrate and texture.", "Used as the primary food ingredient."),
        "refined palmolein oil": ("Vegetable oil", "A refined palm-derived oil used for cooking and texture.", "Used as a cooking fat and to provide crispness and texture."),
        "palmolein oil": ("Vegetable oil", "A refined palm-derived oil used for cooking and texture.", "Used as a cooking fat and to provide crispness and texture."),
        "palm oil": ("Vegetable oil", "A plant-derived oil used for cooking, texture and stability.", "Used as a fat source and to influence product texture."),
        "bengal gram hour": ("Legume flour", "Bengal gram flour is a chickpea-based flour that contributes carbohydrate and plant protein.", "Used to provide body, structure and characteristic flavour."),
        "bengal gram flour": ("Legume flour", "Flour made from Bengal gram (chickpea), providing carbohydrate and plant protein.", "Used to provide body, structure and characteristic flavour."),
        "besan": ("Legume flour", "Chickpea flour made from Bengal gram.", "Used to provide body, structure and flavour."),
        "potato flakes": ("Potato ingredient", "Dehydrated potato pieces used to provide potato solids and texture.", "Used to provide potato flavour, solids and texture."),
        "potato starch": ("Starch", "Starch extracted from potato and used as a carbohydrate-based functional ingredient.", "Used to improve crispness, binding or texture."),
        "tapioca starch": ("Starch", "Starch obtained from cassava/tapioca.", "Used to provide binding, crispness or texture."),
        "starch": ("Starch", "A carbohydrate-based ingredient commonly used for structure and texture.", "Used to thicken, bind or improve texture."),
        "salt": ("Seasoning", "Salt used mainly for flavour and sodium contribution.", "Used to season the product."),
        "sugar": ("Sweetener", "A sweetening ingredient that contributes to sweetness and sugar content.", "Used to provide sweetness."),
        "citric acid": ("Acidity regulator", "An organic acid used to control acidity and provide tartness.", "Used to regulate acidity and flavour."),
        "wheat flour": ("Cereal flour", "Flour made from wheat and used as a carbohydrate and structural ingredient.", "Used to provide structure and bulk."),
        "milk powder": ("Dairy ingredient", "Dried milk solids containing milk proteins and other dairy components.", "Used to provide dairy solids, flavour and body."),
        "lecithin": ("Emulsifier", "A phospholipid used to help oil and water-based components stay mixed.", "Used to improve mixing and product stability."),
        "natural flavour": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "natural flavor": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "preservative": ("Preservative", "An ingredient used to slow deterioration caused by microorganisms.", "Used to help maintain shelf life."),
        "xanthan gum": ("Thickener / stabilizer", "A polysaccharide commonly used to increase viscosity and stabilize texture.", "Used to thicken and stabilize the product."),
        "guar gum": ("Thickener", "A plant-derived gum used to increase viscosity.", "Used to improve thickness and texture."),
        "modified starch": ("Modified starch", "Starch modified for functional food properties.", "Used to improve texture, binding or stability."),
        "colour": ("Food colour", "A colouring ingredient used to provide or restore appearance.", "Used to provide or restore colour."),
        "color": ("Food colour", "A colouring ingredient used to provide or restore appearance.", "Used to provide or restore colour."),
        "flavour": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "flavor": ("Flavouring", "A flavouring ingredient used to provide or enhance taste or aroma.", "Used to provide or enhance flavour."),
        "whey": ("Dairy ingredient", "A milk-derived ingredient containing whey proteins and other milk components.", "Used for dairy solids, protein or functional properties."),
        "butter": ("Dairy fat", "A dairy fat used for flavour and texture.", "Used to provide flavour and fat-based texture."),
        "cheese": ("Dairy ingredient", "A dairy ingredient contributing flavour, protein and texture.", "Used for flavour, texture and dairy solids."),
        "cocoa": ("Cocoa ingredient", "Cocoa solids used to provide chocolate flavour and colour.", "Used to provide chocolate flavour and colour."),
        "vanilla": ("Flavouring", "A flavouring ingredient providing characteristic aroma and taste.", "Used to provide vanilla flavour and aroma."),
    }

    def find_match(item):
        clean = re.sub(r"\\s+", " ", str(item).strip().lower())
        if clean in guide:
            return guide[clean]
        for key in sorted(guide, key=len, reverse=True):
            if key in clean:
                return guide[key]
        return None

    result = []
    for item in raw_items:
        data = find_match(item)
        if data:
            role, description, purpose = data
            confidence = "High"
            source = "ProductLens ingredient knowledge base"
        else:
            role = "Identified ingredient"
            description = "This ingredient is listed in the product database. Its exact technological function depends on the formulation."
            purpose = "Used as part of the product formulation; the package declaration is the primary source for its exact function."
            confidence = "Database-listed"
            source = "Open Food Facts ingredient data"

        result.append({
            "ingredient": item,
            "role": role,
            "code": "",
            "description": description,
            "purpose": purpose,
            "confidence": confidence,
            "source": source
        })

    return result
'''

text = text[:start] + new_function + text[end:]
old = '    product["decoded_ingredients"] = decode_ingredients(\n        ingredients\n    )'
new = '''    product["ingredient_details"] = decode_ingredients(
        ingredients
    )

    product["decoded_ingredients"] = product["ingredient_details"]'''
if old in text:
    text = text.replace(old, new, 1)
elif 'product["ingredient_details"] = decode_ingredients' not in text:
    raise SystemExit("Expected ingredient output assignment was not found")

compile(text, "app.py", "exec")
path.write_text(text, encoding="utf-8")
print("Ingredient Detective repair applied; app.py syntax OK")
