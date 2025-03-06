import json

import streamlit as st
import boto3
import pandas as pd

import utils as u

db = u.get_db()
s3 = boto3.client("s3")
# Note this is different from the other tool.
prices = u.get_new_entries(db.get_all_prices(), ["ingredient_id"])
ingredients = u.get_new_entries(db.get_all_ingredients(), ["id"])

bucket = st.secrets.aws.bucket_name
key_prefix = st.secrets.aws.key_prefix
recipe_key = f"{key_prefix}recipes.json"

try:
    response = s3.get_object(Bucket=bucket, Key=recipe_key)
    recipes = json.loads(response["Body"].read().decode("utf-8"))
    recipes = {k: pd.DataFrame(v) for k, v in recipes.items()}
except s3.exceptions.NoSuchKey:
    recipes = {}


def save_recipes():
    recipes_json = {
        name: df.to_dict("records") if not df.empty else []
        for name, df in recipes.items()
    }
    s3.put_object(
        Body=json.dumps(recipes_json),
        Bucket=bucket,
        Key=recipe_key,
        ContentType="application/json",
    )


# have to do this because i cant use func_format to split written and display values due to a limitation in SelectboxColumn. so having duplicate names would break everything.
if len(ingredients["name"]) != len(ingredients["name"].unique()):
    st.error(
        "Error: Found duplicate ingredient names in your ingredients database. Fix that in DynamoDB or in the Admin panel of the cost input tool."
    )

# recipe_name: ingredient_id, ingredient_name, unit, quantity

st.subheader("New Recipe")

with st.form("new_recipe", clear_on_submit=True):
    new_name = st.text_input("Recipe Name")
    submitted = st.form_submit_button("Create")
    if submitted:
        if new_name in recipes:
            st.error("Recipe Already Exists")
            st.stop()
        recipes[new_name] = pd.DataFrame(
            [
                {
                    "ingredient_id": None,
                    "ingredient_name": "",
                    "unit": "",
                    "quantity": 0,
                    "batch_size": 0,
                }
            ],
            columns=[
                "ingredient_id",
                "ingredient_name",
                "unit",
                "quantity",
                "batch_size",
            ],
        )
        st.session_state.success_new = f"Successfully created {new_name}"
        save_recipes()
        st.rerun()
    if "success_new" in st.session_state:
        st.success(st.session_state.success_new)
        del st.session_state.success_new


st.subheader("Edit Recipe")

edit_recipe = st.selectbox("Recipe", options=recipes.keys())

with st.form("edit_recipe", clear_on_submit=False):
    if edit_recipe:
        edit_df = recipes[edit_recipe].copy()
        if "ingredient_name" in edit_df.columns and "ingredient" not in edit_df.columns:
            edit_df["ingredient"] = edit_df["ingredient_name"]
            edit_df = edit_df.drop(
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
            "batch_size": st.column_config.NumberColumn(
                "Batch Size", min_value=1, step=1, required=True
            ),
        }

        edited_df = st.data_editor(
            data=edit_df,
            use_container_width=True,
            num_rows="dynamic",
            column_config=column_config,
            column_order=[
                "ingredient",
                "unit",
                "quantity",
                "batch_size",
            ],
        )

        submitted = st.form_submit_button("Save Changes")

        if submitted:
            storage_df = edited_df.copy()
            storage_df["ingredient_name"] = storage_df["ingredient"]
            for i, row in storage_df.iterrows():
                ingredient_match = ingredients[ingredients["name"] == row["ingredient"]]
                storage_df.at[i, "ingredient_id"] = ingredient_match.iloc[0]["id"]
            storage_df = storage_df.drop(columns=["ingredient"], errors="ignore")
            recipes[edit_recipe] = storage_df
            save_recipes()
            st.session_state.success_edit = f"Saved Changes to {edit_recipe}"
            st.rerun()
        if "success_edit" in st.session_state:
            st.success(st.session_state.success_edit)
            del st.session_state.success_delete

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
    if "success_delete" in st.session_state:
        st.success(st.session_state.success_delete)
        del st.session_state.success_delete

u.display_df(prices)

st.subheader("Ingredients")

u.display_df(ingredients)
