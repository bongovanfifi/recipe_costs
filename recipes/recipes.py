import json
import sys
from pathlib import Path
import uuid

import streamlit as st
import boto3
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from shared import utils as u

db = u.get_db("recipes")
s3 = boto3.client("s3")
prices = u.get_new_entries(db.get_all_prices(), ["ingredient_id"])
ingredients = u.get_new_entries(db.get_all_ingredients(), ["id"])

bucket = st.secrets.shared_aws.bucket_name
# This could just be another DynamoDB table, that would cut down complexity, but even in free tier that just feels crazy. Once written this will change less than once a month.
recipe_key = f"{st.secrets.shared_aws.key_prefix}recipes.json"

try:
    response = s3.get_object(Bucket=bucket, Key=recipe_key)
    recipes = json.loads(response["Body"].read().decode("utf-8"))
    recipes = {
        k: {
            "batch_size": v["batch_size"],
            "ingredients": pd.DataFrame(v["ingredients"]),
        }
        for k, v in recipes.items()
    }
except s3.exceptions.NoSuchKey:
    recipes = {}


def save_recipes():
    to_save = {}
    for k, v in recipes.items():
        if v["ingredients"].empty:
            ingredients = {
                "ingredient_id": None,
                "ingredient_name": "",
                "unit": "",
                "quantity": 0,
            }
        else:
            ingredients = v["ingredients"].to_dict("records")
        to_save[k] = {"batch_size": v["batch_size"], "ingredients": ingredients}
    s3.put_object(
        Body=json.dumps(to_save),
        Bucket=bucket,
        Key=recipe_key,
        ContentType="application/json",
    )


# I have to do this because I can't use func_format to split written and display values due to a limitation in SelectboxColumn. Having duplicate names would break everything.
if len(ingredients["name"]) != len(ingredients["name"].unique()):
    st.error(
        "Error: Found duplicate ingredient names in your ingredients database. Fix that in DynamoDB or in the Admin panel of the cost input tool."
    )

# recipe_name: ingredient_id, ingredient_name, unit, quantity

st.subheader("New Recipe")

with st.form("new_recipe", clear_on_submit=True):
    new_name = st.text_input("Recipe Name")
    batch_size = st.number_input("Batch Size", min_value=1, step=1)
    submitted = st.form_submit_button("Create")
    if submitted:
        if new_name in recipes:
            st.error(f"Recipe named {new_name} already exists.")
            st.stop()
        recipes[new_name] = {
            # TODO: Name should also just be a normal field and the recipe should get an id so the recipe can get renamed... means I have to rewrite a bunch of this.
            "batch_size": batch_size,
            "ingredients": pd.DataFrame(
                # Streamlit needs this for st.data_editor to work right.
                # TODO: Report getting "This error should never show up please report this" when data_editor empty!
                [
                    {
                        "ingredient_id": None,
                        "ingredient_name": "",
                        "unit": "",
                        "quantity": 0,
                    }
                ],
                columns=[
                    "ingredient_id",
                    "ingredient_name",
                    "unit",
                    "quantity",
                ],
            ),
        }
        st.session_state.success_new = f"Successfully created {new_name}"
        save_recipes()
        st.rerun()
    u.show_success_once("success_new")

st.subheader("Edit Recipe")

edit_recipe = st.selectbox("Recipe", options=recipes.keys())

with st.form("edit_recipe", clear_on_submit=False):
    if edit_recipe:
        edit_ingredients = recipes[edit_recipe]["ingredients"].copy()
        batch_size = st.number_input(
            "Batch Size",
            placeholder=recipes[edit_recipe]["batch_size"],
            step=1,
            min_value=1,
        )
        if (
            "ingredient_name" in edit_ingredients.columns
            and "ingredient" not in edit_ingredients.columns
        ):
            edit_ingredients["ingredient"] = edit_ingredients["ingredient_name"]
            edit_ingredients = edit_ingredients.drop(
                columns=["ingredient_name", "ingredient_id"], errors="ignore"
            )

        column_config = {
            "ingredient": st.column_config.SelectboxColumn(
                "Ingredient",
                options=ingredients["name"].tolist(),
                required=True,
            ),
            "unit": st.column_config.SelectboxColumn(
                "Unit", options=u.available_units, required=True
            ),
            "quantity": st.column_config.NumberColumn(
                "Quantity", min_value=0, required=True
            ),
        }

        edited_ingredients = st.data_editor(
            data=edit_ingredients,
            use_container_width=True,
            num_rows="dynamic",
            column_config=column_config,
            column_order=[
                "ingredient",
                "unit",
                "quantity",
            ],
        )

        submitted = st.form_submit_button("Save Changes")

        if submitted:
            if (
                edited_ingredients.isnull().any().any()
                or (edited_ingredients == "").any().any()
            ):
                st.error("Please fill in all required fields")
                st.stop()
            new_ingredients = edited_ingredients.copy()  # TODO: sloppy naming..
            new_ingredients["ingredient_name"] = new_ingredients["ingredient"]
            for i, row in new_ingredients.iterrows():
                ingredient_match = ingredients[ingredients["name"] == row["ingredient"]]
                new_ingredients.at[i, "ingredient_id"] = ingredient_match.iloc[0]["id"]
            new_ingredients = new_ingredients.drop(
                columns=["ingredient"], errors="ignore"
            )
            recipes[edit_recipe] = {
                "batch_size": batch_size,
                "ingredients": new_ingredients,
            }
            save_recipes()
            st.session_state.success_edit = f"Saved Changes to {edit_recipe}"
            st.rerun()
        u.show_success_once("success_edit")

st.subheader("Delete Recipe")

with st.form(f"delete_recipe", clear_on_submit=True):
    # probably should make harder.
    if recipes:
        delete_recipe = st.selectbox("Recipe to Delete", options=recipes.keys())
        submitted = st.form_submit_button("Delete")
        if submitted:
            del recipes[delete_recipe]
            save_recipes()
            st.session_state.success_delete = f"Deleted {delete_recipe}"
            st.rerun()
    else:
        st.write("No Recipes to Delete")
        submitted = st.form_submit_button("Delete", disabled=True)
    u.show_success_once("success_delete")

u.display_df(prices)

st.subheader("Ingredients")

u.display_df(ingredients)
