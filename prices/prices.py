import streamlit as st
import datetime as dt
from sqlalchemy import text
import sys
from pathlib import Path
import time

sys.path.append(str(Path(__file__).parent.parent))
import shared.utils as u
import pandas as pd


# TODO: This is a bad way of authenticating. A week or two after I added it, streamlit added st.login(), but at time of writing it's still in the expiremental phase. Replace all this dumb sqlite stuff with st.login() when it's stable.

# TODO: needs real error handling...

if not u.check_password("kitchen"):
    st.stop()


st.title("Ingredient Cost Entry")

db = u.get_db("prices")
ingredients = db.get_all_ingredients()
if ingredients.empty:
    st.error("No ingredients found.")
    st.stop()
ingredients = u.get_new_entries(ingredients, ["id"])
prices = db.get_all_prices()
if not prices.empty:
    prices = u.get_new_entries(prices, ["ingredient_id"])


def display_ingredient_status():
    if prices.empty:
        st.info("No prices recorded yet, all prices missing")
        return

    st.subheader("Missing Ingredient Prices")

    missing = ingredients[~ingredients["id"].isin(prices["ingredient_id"].unique())]
    if missing.empty:
        st.success("✅ No Missing Ingredients")
    else:
        st.dataframe(missing["name"], use_container_width=True)
    st.subheader("Prices More Than 90 Days Old")
    old_prices = prices[
        prices["timestamp"] <= int(time.time()) - 7776000
    ]  # 90 days in seconds
    if not old_prices.empty:
        old_with_names = pd.merge(
            old_prices,
            ingredients,
            left_on="ingredient_id",
            right_on="id",
            how="left",
        )
        old_with_names["last_updated"] = pd.to_datetime(
            old_with_names["timestamp"], unit="s"
        )
        u.display_df(old_with_names)
    else:
        st.success("✅ All prices that are not missing are up to date")

    st.subheader("Current Prices")
    u.display_df(prices)


with st.expander("How To Use This Tool"):
    st.write(
        """First, select the ingredient, then enter the cost of the ingredient and unit it is sold in (whether it's sold by the pound, the gallon, etc). Finally enter the quantity and hit save. The order you enter these things in doesn't matter.
             
You don't have to calculate the cost per unit or anything. That's automated.
             
Don't select "unit" in the unit field for things that are not used "by unit". For example, "Forminha" isn't used by weight, one is used every time. If you buy 1000 at a time, you would enter the quantity as 1000, and "unit" would be the unit. However, flour is not by unit, so enter the number of pounds/kg/etc purchased."""
    )
    st.warning(
        """When you enter a price you should see it removed from the missing prices and added to current prices immediately! If the tool isn't showing the price you entered, or is otherwise not responding, it didn't save the price. This should never happen, but if it does, stop entering prices and email me at giovanni.b.boff@gmail.com and I'll fix the tool."""
    )


with st.form("price_entry", clear_on_submit=True):
    ingredient_id = st.selectbox(
        "Ingredient",
        options=ingredients["id"].tolist(),
        format_func=lambda id: ingredients[ingredients["id"] == id]["name"].iloc[0],
    )
    selected_ingredient = ingredients[ingredients["id"] == ingredient_id].iloc[0]

    price = st.number_input(
        "Cost ($)", min_value=0.00, step=0.01, format="%.2f", key="cost"
    )

    unit = st.selectbox("Unit", u.available_units, key="unit")

    quantity = st.number_input("Quantity", min_value=0, key="quantity")

    if st.form_submit_button("Save"):
        if price <= 0 or quantity <= 0:
            st.exception(ValueError("Cost and quantity must be greater than 0"))
        elif round(price, 2) != price:
            st.error("Cost cannot have more than 2 decimal places")
        else:
            try:
                db.put_price(
                    selected_ingredient["name"], ingredient_id, price, unit, quantity
                )
                st.session_state.success_price_add = (
                    f"""Added {selected_ingredient["name"]}"""
                )
                st.rerun()
            except Exception as e:
                st.exception(e)
        u.show_success_once("success_price_add")

display_ingredient_status()
