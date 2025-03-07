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


def check_password():
    """Check if user has kitchen password with persistent rate limiting"""
    if st.session_state.get("authenticated"):
        return True
    ip = st.query_params.get("client_ip", ["unknown"])[0]
    with u.get_local_connection().session as session:
        lockout = session.execute(
            text("SELECT attempts, last_attempt FROM lockouts WHERE ip = :ip"),
            {"ip": ip},
        ).fetchone()
        current_time = int(dt.datetime.now().timestamp())
        if lockout and lockout.attempts >= 10:
            if current_time - lockout.last_attempt < 300:
                st.error("Too many attempts. Please wait 5 minutes.")
                time.sleep(2)
                return False
            else:
                session.execute(
                    text("UPDATE lockouts SET attempts = 0 WHERE ip = :ip"), {"ip": ip}
                )
                session.commit()

    with st.form("login", clear_on_submit=True):
        password = st.text_input("Password", type="password", key="pwd")
        submitted = st.form_submit_button("Login")
        if submitted:
            if (
                password == st.secrets.passwords.kitchen
                or password == st.secrets.passwords.admin
            ):
                st.session_state.authenticated = True
                st.rerun()
                return True
            else:
                with u.get_local_connection().session as session:
                    session.execute(
                        text(
                            """
                            INSERT INTO lockouts (ip, attempts, last_attempt) 
                            VALUES (:ip, 1, :time)
                            ON CONFLICT(ip) DO UPDATE SET 
                            attempts = attempts + 1,
                            last_attempt = :time
                        """
                        ),
                        {"ip": ip, "time": current_time},
                    )
                    session.commit()
                st.error("Incorrect password")
                time.sleep(1)
                return False
    return False


if not check_password():
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
                st.success(f"""{selected_ingredient["name"]} price saved!""")
            except Exception as e:
                st.exception(e)

display_ingredient_status()
